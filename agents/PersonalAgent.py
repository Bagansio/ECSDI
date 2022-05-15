# -*- coding: utf-8 -*-
"""
filename: PersonalAgent

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

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = agents.agent_ports['PersonalAgent']
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
PersonalAgent = Agent('PersonalAgent',
                       agn.PersonalAgent,
                       'http://%s:%d/comm' % (hostaddr, port),
                       'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()



# Agent Utils


def agregarDBProducto(data):
    try:
        logger.info("Registrando producto: [" + data['Nombre'] + " " + data['Marca'] +
                    "] de " + data['Peso'] + "kg por " + data['Precio'] + "€")
        # añadir el producto
        global mss_cnt
        ontologyFile = open(db.DBProductos)
        graph = Graph()
        graph.parse(ontologyFile, format='turtle')
        graph.bind("default", ECSDI)
        id = 'Producto' + str(uuid.uuid4())
        item = ECSDI[id]

        graph.add((item, RDF.type, ECSDI.Product))
        graph.add((item, ECSDI.Nombre, Literal(data['Nombre'], datatype=XSD.string)))
        graph.add((item, ECSDI.Precio, Literal(data['Precio'], datatype=XSD.float)))
        graph.add((item, ECSDI.Categoria, Literal(data['Categoria'], datatype=XSD.string)))
        graph.add((item, ECSDI.Peso, Literal(data['Peso'], datatype=XSD.float)))
        graph.add((item, ECSDI.Marca, Literal(data['Marca'], datatype=XSD.string)))
        graph.add((item, ECSDI.Externo, Literal(data['Externo'], datatype=XSD.boolean)))


        graph.serialize(destination=db.DBProductos, format='turtle')
        logger.info("Registro de nuevo producto finalizado")

    except Exception as e:
        print(e)
        logger.info("Registro de nuevo producto fallido")


def procesarProducto(graph, content):
    data = {
        'Categoria': None,
        'Marca': None,
        'Nombre': None,
        'Peso': None,
        'Precio': None,
        'Externo': None
    }

    for a,b,c in graph:

        if 'Peticion' in a and b == ECSDI.Categoria:
            data['Categoria'] = c

        elif 'Peticion' in a and b == ECSDI.Marca:
            data['Marca'] = c

        elif 'Peticion' in a and  b == ECSDI.Nombre:
            data['Nombre'] = c

        elif 'Peticion' in a and b == ECSDI.Peso:
            data['Peso'] = c

        elif 'Peticion' in a and b == ECSDI.Precio:
            data['Precio'] = c

        elif 'Peticion' in a and b == ECSDI.Externo:
            data['Externo'] = c


    agregarDBProducto(data)

# Agrega un Producto Externo a la BD
def agregarproducto(content, gm):
    logger.info("Recibida peticion de añadir productos")
    for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
        print(item)
        gm.remove((item, None, None))

    thread = threading.Thread(target=procesarProducto, args=(gm, content))
    thread.start()

    resultadoComunicacion = Graph()

    return resultadoComunicacion


def search_agent(agent_name):
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    logger.info('Buscamos a ' + agent_name)

    global mss_cnt

    gmess = Graph()

    # Construimos el mensaje de registro
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    reg_obj = agn[agent_name + '-Search']
    gmess.add((reg_obj, RDF.type, DSO.Search))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=PersonalAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr


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
    reg_obj = agn[PersonalAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, PersonalAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(PersonalAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(PersonalAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.PersonalAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=PersonalAgent.uri,
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
    agent = agents.get_agent(DSO.GestorProductosAgent, PersonalAgent, DirectoryAgent, mss_cnt)
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
            Graph(), ACL['not-understood'], sender=PersonalAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=PersonalAgent.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

                if accion == ECSDI.PeticionAgregarProducto:
                    gr = agregarproducto(content, gm)
            # Aqui realizariamos lo que pide la accion
            # Por ahora simplemente retornamos un Inform-done
            gr = build_message(Graph(),
                               ACL['inform'],
                               sender=PersonalAgent.uri,
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
