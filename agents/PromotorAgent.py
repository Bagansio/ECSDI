# -*- coding: utf-8 -*-
"""
filename: PromotorAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente de hoteles y espera peticiones

@author: Bagansio, Cristian Mesa, Artur Farriols
"""

from pathlib import Path
import sys

path_root = Path(__file__).resolve().parents[1]
sys.path.append(str(path_root))

from multiprocessing import Process, Queue
import logging
import argparse
import threading
import uuid

from flask import Flask, request,render_template
from rdflib import Graph, Namespace, Literal, URIRef, XSD
from rdflib.namespace import FOAF, RDF
from utils import db,agents
import random

from AgentUtil.OntoNamespaces import ECSDI
from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname
import socket
from threading import Thread


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

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9004
else:
    port = args.port

if args.open:
    hostname = '0.0.0.0'
    hostaddr = gethostname()

else:
    hostaddr = hostname = socket.gethostname()

print('DS Hostname =', hostaddr)

if args.dport is None:
    dport = 9000
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
PromotorAgent = Agent('PromotorAgent',
                  agn.PromotorAgent,
                  'http://%s:%d/comm' % (hostaddr, port),
                  'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

GestorProductosAgent = None

# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()


def recomendar(content, gm):
    global mss_cnt
    global DirectoryAgent
    global PromotorAgent
    global GestorProductosAgent

    if GestorProductosAgent is None:
        GestorProductosAgent = agents.get_agent(DSO.GestorProductosAgent, PromotorAgent, DirectoryAgent, mss_cnt)

    graph_message = Graph()
    graph_message.bind('foaf', FOAF)
    graph_message.bind('dso', DSO)
    graph_message.bind("default", ECSDI)
    reg_obj = ECSDI['PeticionProductos' + str(mss_cnt)]
    graph_message.add((reg_obj, RDF.type, ECSDI.PeticionProductos))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    graph = send_message(
        build_message(graph_message, perf=ACL.request,
                      sender=PromotorAgent.uri,
                      receiver=GestorProductosAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        GestorProductosAgent.address)

    mss_cnt += 1

    query = """
        prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        prefix xsd:<http://www.w3.org/2001/XMLSchema#>
        prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
        prefix owl:<http://www.w3.org/2002/07/owl#>
        SELECT ?producto ?nombre ?precio ?marca ?peso ?categoria ?descripcion ?externo ?valoracion
            where {
            {?producto rdf:type default:Producto } .
            ?producto default:Nombre ?nombre .
            ?producto default:Precio ?precio .
            ?producto default:Marca ?marca .
            ?producto default:Peso ?peso .
            ?producto default:Categoria ?categoria .
            ?producto default:Descripcion ?descripcion .
            ?producto default:Externo ?externo .
            ?producto default:Valoracion ?valoracion . }"""

    productos = graph.query(query)

    recomendacion = random.choice(list(productos))

    gm = Graph()
    gm.bind("ECSDI", ECSDI)  # posible cambio
    sujetoRespuesta = ECSDI['RespuestaDeRecomendacion' + str(uuid.uuid4())]

    # mss_cnt += 1
    gm.add((sujetoRespuesta, RDF.type, ECSDI.RespuestaRecomendacion))
    gm.add((sujetoRespuesta, ECSDI.Producto, recomendacion['producto']))
    gm.add((recomendacion['producto'], RDF.type, ECSDI.Producto))
    gm.add((recomendacion['producto'], ECSDI.Nombre, recomendacion['nombre']))
    gm.add((recomendacion['producto'], ECSDI.Precio, recomendacion['precio']))
    gm.add((recomendacion['producto'], ECSDI.Marca, recomendacion['marca']))
    gm.add((recomendacion['producto'], ECSDI.Peso, recomendacion['peso']))
    gm.add((recomendacion['producto'], ECSDI.Categoria, recomendacion['categoria']))
    gm.add((recomendacion['producto'], ECSDI.Externo, recomendacion['externo']))
    gm.add((recomendacion['producto'], ECSDI.Valoracion, recomendacion['valoracion']))
    gm.add((recomendacion['producto'], ECSDI.Descripcion, recomendacion['descripcion']))

    return gm





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
    reg_obj = agn[PromotorAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, PromotorAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(PromotorAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(PromotorAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.PromotorAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=PromotorAgent.uri,
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
    return 'Nothing to see here'


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
            Graph(), ACL['not-understood'], sender=PromotorAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=PromotorAgent.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro
            response = Graph()
            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

                for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                    gm.remove((item, None, None))

                if accion == ECSDI.RecomendarProducto:
                    response = recomendar(content, gm)

            # Aqui realizariamos lo que pide la accion
            # Por ahora simplemente retornamos un Inform-done
            gr = build_message(response,
                               ACL['inform'],
                               sender=PromotorAgent.uri,
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