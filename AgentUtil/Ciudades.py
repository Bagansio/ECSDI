from multiprocessing import Process, Queue
import argparse
import math

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
from threading import Thread

ciudades = {
    "Barcelona": [7, 6],
    "Berga": [2, 5],
    "Figueres": [1, 8],
    "Girona": [4, 7],
    "Lloret": [5, 9],
    "Manresa": [5, 4],
    "Mataro": [6, 7],
    "Reus": [8, 2],
    "Sabadell": [6, 6],
    "Salou": [9, 2],
    "Tarragona": [8, 3],
    "Urgell": [2, 3]
}

def centrosMasProximos (ciudad):


    centrosLogisticos = {
        "CentroLogisticoAgent1" : [6, 5],
        "CentroLogisticoAgent2" : [2, 7],
        "CentroLogisticoAgent3" : [8, 1]
    }

    distancias = {}
    centroActual = 1

    for values in centrosLogisticos.values():
        dist = math.sqrt(abs(ciudades[ciudad][0] - values[0]) ** 2 + abs(ciudades[ciudad][1] - values[1]) ** 2)
        distancias["CentroLogisticoAgent" + str(centroActual)] = dist
        centroActual += 1
    
    print(distancias['CentroLogisticoAgent1'])
    print(distancias['CentroLogisticoAgent2'])
    print(distancias['CentroLogisticoAgent3'])


    distanciasOrdenadas = dict(sorted(distancias.items(), key=lambda item: item[1]))



    resultado = []

    for key in distanciasOrdenadas:
        resultado.append(key)

    return resultado