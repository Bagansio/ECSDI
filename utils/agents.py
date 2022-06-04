import requests
from AgentUtil.Agent import Agent
from rdflib import Graph, Namespace, Literal, URIRef, XSD
from flask import Flask, request,render_template
from rdflib import Graph, Namespace, Literal, URIRef, XSD
from rdflib.namespace import FOAF, RDF
import datetime
import random
from AgentUtil.OntoNamespaces import ECSDI
from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname

agn = Namespace("http://www.agentes.org#")

agent_ports = {'GestorProductosAgent': 9001,
               'GestorServicioExternoAgent': 9002,
               'PersonalAgent': 9003,
               'MostradorAgent': 9004,
               'CentroLogisticoAgent': 9005,
               
               'VendedorAgent':9010,
               
               'GestorEnviosAgent':9011,
               'GestorDevolucionesAgent': 9012,
               'TesoreroAgent':9013,


               'Transportista1Agent': 9015,
               'Transportista2Agent': 9016,
               }

def get_agent(agn_type, sender, reciever, mss_cnt):

    gmess = Graph()

    # Construimos el mensaje de búsqueda
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    sear_obj = agn[sender.name + '-Search']
    gmess.add((sear_obj, RDF.type, DSO.Search))
    gmess.add((sear_obj, DSO.AgentType, agn_type))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=sender.uri,
                      receiver=reciever.uri,
                      content=sear_obj,
                      msgcnt=mss_cnt),
        reciever.address)

    msg_dic = get_message_properties(gr)
    content = msg_dic['content']

    address = gr.value(subject=content, predicate=DSO.Address)
    url = gr.value(subject=content, predicate=DSO.Uri)
    name = gr.value(subject=content, predicate=FOAF.name)

    return Agent(name, url, address, None)

def print_graph(graph):
    for a,b,c in graph:
        print(a)
        print(b)
        print(c)
        print("-------------------------------------------------------------------------")


def get_date(prioridad):

    date = datetime.date.today()
    days = 1
    if prioridad == 1:
        days = random.choice((3,4,5))
    elif prioridad == 0:
        days = random.choice((5,6,7,8,9,10))

    return date + datetime.timedelta(days=days)