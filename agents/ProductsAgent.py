# -*- coding: utf-8 -*-
"""
filename: ProductsAgent

Agent that registry as product agent and waits for requests


@author: Bagansio
"""
from pathlib import Path
import sys

path_root = Path(__file__).parents[1]
sys.path.append(str(path_root))

from multiprocessing import Process, Queue
import socket

from rdflib import Namespace, Graph, logger, RDF, XSD, Literal, URIRef, FOAF
from flask import Flask, request

from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.ACL import ACL
from AgentUtil.DSO import DSO


__author__ = 'Bagansio'

# Configuration stuff
hostname = socket.gethostname()
port = 9001

agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

ProductsAgent = Agent('ProductsAgent',
                       agn.ProductsAgent,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)

# Global triplestore graph
dsgraph = Graph()

queue = Queue()

# Flask stuff
app = Flask(__name__)


#####################
## AGENT FUNCTIONS ##
#####################

def get_count():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt


def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    logger.info('We registered')

    global mss_cnt

    gmess = Graph()

    # Construimos el mensaje de registro
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    reg_obj = agn[ProductsAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, ProductsAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(ProductsAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(ProductsAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.HotelsAgent))
    print(gmess)
    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=ProductsAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1
    
    return gr

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
    gm.parse(data=message)

    msgdic = get_message_properties(gm)

    # Comprobamos que sea un mensaje FIPA ACL
    if msgdic is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(
            Graph(), ACL['not-understood'], sender=ProductsAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=ProductsAgent.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

            # Aqui realizariamos lo que pide la accion
            # Por ahora simplemente retornamos un Inform-done
            gr = build_message(Graph(),
                               ACL['inform'],
                               sender=ProductsAgent.uri,
                               msgcnt=mss_cnt,
                               receiver=msgdic['sender'], )
    mss_cnt += 1

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


@app.route("/Stop")
def stop():
    """
    Entrypointthat stops the agent
    :return:
    """
    tidyup()
    shutdown_server()
    return "Stopping the server"


def tidyup():
    """
    Actions prior to stopping the agent
    """
    global queue
    queue.put(0)


def agent_behavior(queue):
    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    # Registramos el agente
    gr = register_message()

    # Escuchando la cola hasta que llegue un 0
    fin = False
    while not fin:
        while queue.empty():
            pass
        v = queue.get()
        if v == 0:
            fin = True
        else:
            print(v)


# AGENT FUNCTIONS


# MAIN METHOD

if __name__ == '__main__':
    # Start and run behaviors
    ab1 = Process(target=agent_behavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port)

    # Wait behaviors
    ab1.join()
    print('The End')

