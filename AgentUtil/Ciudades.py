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


def centrosMasProximos (ciudad):
    ciudades = {
        "Barcelona" : [7, 6],
        "Berga" : [2, 5],
        "Figueres" : [1, 8],
        "Girona" : [4, 7],
        "Lloret" : [5, 9],
        "Manresa" : [5, 4],
        "Mataro" : [6, 7],
        "Reus" : [8, 2],
        "Sabadell" : [6, 6],
        "Salou" : [9, 2],
        "Tarragona" : [8, 3],
        "Urgell" : [2, 3]
    }

    centrosLogisticos = {
        "CentroLogistico1" : [6, 5],
        "CentroLogistico2" : [2, 7],
        "CentroLogistico3" : [8, 1]
    }

    distancias = {}
    centroActual = 1

    for values in centrosLogisticos.values():
        dist = math.sqrt(abs(ciudades[ciudad][0] - values[0]) ** 2 + abs(ciudades[ciudad][1] - values[1]) ** 2)
        distancias["CentroLogistico" + str(centroActual)] = dist
        centroActual += 1

    dict(sorted(distancias.items(), key=lambda item: item[1]))

    resultado = []

    for key in distancias:
        resultado.append(key)

    return resultado