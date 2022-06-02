# -*- coding: utf-8 -*-
"""
filename: MostradorAgent
Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

A este agente hay que pasarle un grafo con:
    numTarjeta 
    prioridad 
    direccion 
    codigoPostal 
    idCompra
    Productos

Y guarda en DBCompras la factura.


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

from AgentUtil.OntoNamespaces import ECSDI
from AgentUtil.ACL import ACL
from AgentUtil.Ciudades import centrosMasProximos
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname
import socket
from threading import Thread



__author__ = 'Artur, Cristian'

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
    port = agents.agent_ports['GestorEnviosAgent']
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

# Gestor envio agfent
GestorEnviosAgent = Agent('GestorEnviosAgent',
                                   agn.GestorEnviosAgent,
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


def solicitarDevolucion(content, gm):
    return None


def solicitarEnvio(content, gm):
    logger.info("SolicitarEnvio")
    ontologyFile = open(db.DBCentrosLogisticos)
    centrosLogisticos = Graph()
    centrosLogisticos.parse(ontologyFile, format='turtle')

    ciudad = gm.value(subject=content, predicate=ECSDI.Ciudad)

    #centrosMasCercanos = centrosMasProximos(ciudad) 

    logger.info("Previo al for")
    #for centro in centrosMasCercanos:
        #print (centro)

    r = Graph()
    return r


def obtenerCentrosLogiticos():

    ontologyFile = open(db.DBCentrosLogisticos)
    resultado = Graph()
    resultado.parse(ontologyFile, format='turtle')

    query = """
                        prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                        prefix xsd:<http://www.w3.org/2001/XMLSchema#>
                        prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
                        prefix owl:<http://www.w3.org/2002/07/owl#>
                        SELECT ?centrologistico ?nombre ?posicionx ?posiciony ?almacena 
                            where {
                            {?centrologistico rdf:type default:CentroLogistico } .
                            ?centrologistico default:Nombre ?nombre .
                            ?centrologistico default:PosicionX ?posicionx .
                            ?centrologistico default:PosicionY ?posiciony .
                            ?centrologistico default:Almacena ?almacena .
                            }
                            """
    return resultado.query(query)







@app.route("/info")
def info():
    """
    XD
    """
    global DirectoryAgent
    global GestorEnviosAgent

    gmess = Graph()

    # Construimos el mensaje de búsqueda
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    sear_obj = agn[GestorEnviosAgent.name + '-MultipleSearch']
    gmess.add((sear_obj, RDF.type, DSO.MultipleSearch))
    gmess.add((sear_obj, DSO.AgentType, DSO.CentroLogisticoAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=GestorEnviosAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=sear_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)



    agents.print_graph(gr)

    return "Parando Servidor"








    
@app.route("/stop")
def stop():
    """
    Entrypoint que para el agente
    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"

#comm AQUI
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
            Graph(), ACL['not-understood'], sender=GestorEnviosAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=GestorEnviosAgent.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            logger.info("Previo al if content")
            if 'content' in msgdic:
                response = Graph()
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

                print (content)
                print (accion)
                #for a,b,c in gm:
                    #print(a)
                    #print(b)
                    #print(c)

                if accion == ECSDI.EnvioCompra: #AÑADIR EN LA ONTOLOGIA
                    logger.info("Accion correcta")

                    print(len(gm))
                    for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                        gm.remove((item, None, None))

                    print(len(gm))
                    response = solicitarEnvio(content, gm) #retornamos la fecha y el transportista

                elif accion == ECSDI.EnvioDevolucion: #AÑADIR EN LA ONTOLOGIA

                        print(len(gm))
                        for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                            gm.remove((item, None, None))

                        print(len(gm))
                        response = solicitarDevolucion(content, gm) #retornamos la fecha y el transportista


                gr = build_message(response,
                               ACL['inform'],
                               sender=GestorEnviosAgent.uri,
                               msgcnt=mss_cnt,
                               receiver=msgdic['sender'], )

    mss_cnt += 1

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


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
    reg_obj = agn[GestorEnviosAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, GestorEnviosAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(GestorEnviosAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(GestorEnviosAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.GestorEnviosAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=GestorEnviosAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr


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