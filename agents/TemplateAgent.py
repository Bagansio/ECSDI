# -*- coding: utf-8 -*-
"""
Created on Fri Dec 27 15:58:13 2013
Esqueleto de agente usando los servicios web de Flask
/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente
Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente
Asume que el agente de registro esta en el puerto 9000
@author: javier
"""
from pathlib import Path
import sys

path_root = Path(__file__).parents[1]
sys.path.append(str(path_root))

from multiprocessing import Process, Queue
import socket

from rdflib import Namespace, Graph
from flask import Flask

from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent

__author__ = 'javier'

# Configuration stuff
hostname = socket.gethostname()
port = 9010

agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

TemplateAgent = Agent('TemplateAgent',
                       agn.TemplateAgent,
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


@app.route("/comm")
def comunicacion():
    """
    Entrypoint of communication
    """
    global dsgraph
    global mss_cnt
    pass


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
    pass


def agent_behavior(queue):
    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    pass


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

