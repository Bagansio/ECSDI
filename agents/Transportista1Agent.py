# -*- coding: utf-8 -*-
"""
filename: Transportista1Agent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente personal, envia y espera peticiones

@author: Bagansio, Cristian Mesa, Artur Farriols
"""

from pathlib import Path
import sys

path_root = Path(__file__).parents[1]
sys.path.append(str(path_root))

from multiprocessing import Process, Queue
import logging
import argparse
import threading
import uuid
import random

from flask import Flask, request,render_template
from rdflib import Graph, Namespace, Literal, URIRef, XSD
from rdflib.namespace import FOAF, RDF
from utils import db,agents

from AgentUtil.OntoNamespaces import ECSDI
from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname
import socket

__author__ = 'Bagansio'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor esta abierto al exterior o no", action='store_true',
                    default=False)
parser.add_argument('--verbose', help="Genera un log de la comunicacion del servidor web", action='store_true',
                    default=False)
parser.add_argument('--port', type=int,
                    help="Puerto de comunicacion del agente")
parser.add_argument('--dhost', help="Host del agente de directorio")
parser.add_argument('--dport', type=int,
                    help="Puerto de comunicacion del agente de directorio")

parser.add_argument('--centro', type=int,
                    help="Id del Centro Logistico")

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = agents.agent_ports['Transportista1Agent']
else:
    port = args.port

if args.open:
    hostname = '0.0.0.0'
    hostaddr = gethostname()
else:
    hostaddr = hostname = socket.gethostname()

print('DS Hostname =', hostaddr)

if args.dport is None:
    dport = agents.agent_ports['CentroLogisticoAgent']
else:
    dport = args.dport

if args.dhost is None:
    dhostname = socket.gethostname()
else:
    dhostname = args.dhost

# Flask stuff
app = Flask(__name__)
if not args.verbose:
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

# Configuration constants and variables
agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente
TransportistaAgent = Agent('Transportista1Agent',
                           agn.Transportista1Agent,
                           'http://%s:%d/comm' % (hostaddr, port),
                           'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
DirectoryAgent = Agent('CentroLogisticoAgent' + str(args.centro),
                       agn['CentroLogisticoAgent' + str(args.centro)],
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

TransportistaNombre = "Seul"

# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()



# Agent Utils


def prepararContraOferta(content, grafo_entrada):
    global mss_cnt

    logger.info("Recibida petición contra oferta")

    peso = grafo_entrada.value(subject=content, predicate=ECSDI.Peso)
    precioOferta = grafo_entrada.value(subject=content, predicate=ECSDI.Precio)

    precio = calcularContraOferta(float(peso), precioOferta)

    bajar = True
    if precioOferta <= precio:
        bajar = False

    gm = Graph()
    gm.bind('default', ECSDI)
    logger.info("Haciendo contra oferta de transporte")
    item = ECSDI['RespuestaContraOfertaTransporte' + str(mss_cnt)]
    gm.add((item, RDF.type, ECSDI.RespuestaOfertaTransporte))
    logger.info("Devolvemos oferta de transporte")
    gm.add((item, ECSDI.Precio, Literal(precio, datatype=XSD.float)))
    gm.add((item, ECSDI.Bajar, Literal(bajar, datatype=XSD.boolean)))
    gm.add((item, ECSDI.Nombre, Literal(TransportistaNombre, datatype=XSD.string)))

    return gm


def calcularContraOferta(peso,precioOferta):
    precio = calcularOferta(peso)

    if precioOferta <= precio:
        bajar = random.choice((True, False))
        if bajar:
            precio = abs(precioOferta - 1.)
    return precio

def prepararOferta(content, grafo_entrada):

    global mss_cnt
    global TransportistaNombre

    logger.info("Recibida petición oferta")

    peso = grafo_entrada.value(subject=content, predicate=ECSDI.Peso)

    precio = calcularOferta(float(peso))
    gm = Graph()
    gm.bind('default', ECSDI)
    logger.info("Haciendo oferta de transporte")
    item = ECSDI['RespuestaOfertaTransporte' + str(mss_cnt)]
    gm.add((item, RDF.type, ECSDI.RespuestaOfertaTransporte))
    logger.info("Devolvemos oferta de transporte")
    gm.add((item, ECSDI.Precio, Literal(precio, datatype=XSD.float)))
    gm.add((item, ECSDI.Precio, Literal(precio, datatype=XSD.float)))
    gm.add((item, ECSDI.Nombre, Literal(TransportistaNombre, datatype=XSD.string)))
    return gm

def calcularOferta(peso):
    logger.info("Calculando oferta")
    oferta = round(peso * 1.05, 2)

    logger.info("Oferta calculada de " + str(peso) + "kg: " + str(oferta) + "€")
    return oferta


# Agent functions

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    logger.info('Nos registramos')

    global mss_cnt

    gmess = Graph()

    # Construimos el mensaje de registro
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    reg_obj = agn[TransportistaAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, TransportistaAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(TransportistaAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(TransportistaAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.TransportistaAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=TransportistaAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr


@app.route("/iface", methods=['GET', 'POST'])
def browser_iface():
    """
    Permite la comunicacion con el agente via un navegador
    via un formulario
    """
    global mss_cnt
    mss_cnt += 1

    logger.info('Buscando al agente Gestor Productos')
    agent = agents.get_agent(DSO.GestorProductosAgent, TransportistaAgent, DirectoryAgent, mss_cnt)
    print(agent.name)
    print(agent.uri)
    print(agent.address)

    return render_template('agregarproducto.html')


@app.route("/stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


@app.route("/comm")
def comunicacion():
    """
    Entrypoint de comunicacion del agente
    Simplemente retorna un objeto fijo que representa una
    respuesta a una busqueda de hotel

    Asumimos que se reciben siempre acciones que se refieren a lo que puede hacer
    el agente (buscar con ciertas restricciones, reservar)
    Las acciones se mandan siempre con un Request
    Prodriamos resolver las busquedas usando una performativa de Query-ref
    """
    global dsgraph
    global mss_cnt

    logger.info('Peticion de informacion recibida')

    # Extraemos el mensaje y creamos un grafo con el
    message = request.args['content']
    gm = Graph()
    gm.parse(data=message, format='xml')

    msgdic = get_message_properties(gm)

    # Comprobamos que sea un mensaje FIPA ACL
    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(
            Graph(), ACL['not-understood'], sender=TransportistaAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=TransportistaAgent.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro
            grafo_response = Graph()
            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

                if accion == ECSDI.PedirOferta:

                    for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                        gm.remove((item, None, None))

                    grafo_response = prepararOferta(content, gm)

                if accion == ECSDI.PedirContraOferta:

                    for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                        gm.remove((item, None, None))

                    grafo_response = prepararContraOferta(content, gm)
            # Aqui realizariamos lo que pide la accion
            # Por ahora simplemente retornamos un Inform-done

            gr = build_message(grafo_response,
                               ACL['inform'],
                               sender=TransportistaAgent.uri,
                               msgcnt=mss_cnt,
                               receiver=msgdic['sender'], )
    mss_cnt += 1

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


def tidyup():
    """
    Acciones previas a parar el agente

    """
    global cola1
    cola1.put(0)


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    # Registramos el agente
    gr = register_message()

    # Escuchando la cola hasta que llegue un 0
    fin = False
    while not fin:
        while cola.empty():
            pass
        v = cola.get()
        if v == 0:
            fin = True
        else:
            print(v)



if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    logger.info('The End')
