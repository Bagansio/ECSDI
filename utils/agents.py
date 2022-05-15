import requests
from AgentUtil.Agent import Agent
from rdflib import Graph, Namespace, Literal, URIRef, XSD
from flask import Flask, request,render_template
from rdflib import Graph, Namespace, Literal, URIRef, XSD
from rdflib.namespace import FOAF, RDF

from AgentUtil.OntoNamespaces import ECSDI
from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname

agn = Namespace("http://www.agentes.org#")

agent_ports = {'GestorProductosAgent': 9001, 'GestorServicioExternoAgent': 9002, 'PersonalAgent': 9003, 'MostradorAgent': 9004}


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