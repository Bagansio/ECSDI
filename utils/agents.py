import requests
from AgentUtil.Agent import Agent
from rdflib import Graph, Namespace, Literal, URIRef, XSD



agent_ports = {'GestorProductosAgent': 9001, 'GestorServicioExternoAgent': 9002,}
