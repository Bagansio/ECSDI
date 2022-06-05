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
import datetime

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



__author__ = 'Alex, Artur, Cristian'

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
    port = agents.agent_ports['GestorDevolucionesAgent']
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
GestorDevolucionesAgent = Agent('GestorDevolucionesAgent',
                                   agn.GestorDevolucionesAgent,
                                   'http://%s:%d/comm' % (hostaddr, port),
                                   'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))



VendedorAgent = None

GestorEnviosAgent = None

TesoreroAgent = None

# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()


def pedirReintegro(grafo, content):

    global TesoreroAgent
    global VendedorAgent
    global GestorDevolucionesAgent
    global GestorEnviosAgent
    global DirectoryAgent
    global mss_cnt

    if TesoreroAgent is None:
        TesoreroAgent = agents.get_agent(DSO.TesoreroAgent, VendedorAgent, DirectoryAgent, mss_cnt)

    logger.info("Trata de enviar peticion reintegro a Tesorero Agent")
    gr = send_message(
        build_message(grafo, perf=ACL.request,
                        sender=VendedorAgent.uri,
                        receiver=TesoreroAgent.uri,
                        content=content,
                        msgcnt=mss_cnt),
        TesoreroAgent.address)

    logger.info("Petición de reintegro realizada")

def solicitarEnvio(grafo, content, factura, producto, usuario):
    global TesoreroAgent
    global VendedorAgent
    global GestorDevolucionesAgent
    global GestorEnviosAgent
    global DirectoryAgent
    global mss_cnt

    logger.info("Trata de enviar peticion de Envio al Gestor Envios Agent")
    try:

        if GestorEnviosAgent is None:
            GestorEnviosAgent = agents.get_agent(DSO.TesoreroAgent, VendedorAgent, DirectoryAgent, mss_cnt)


        gr = send_message(
            build_message(grafo, perf=ACL.request,
                            sender=VendedorAgent.uri,
                            receiver=GestorEnviosAgent.uri,
                            content=content,
                            msgcnt=mss_cnt),
            GestorEnviosAgent.address)

        ontologyFile = open(db.DBDevoluciones)
        devos = Graph()
        devos.parse(ontologyFile, format='turtle')

        content = list(gr.triples((None, ECSDI.Precio, None)))[0][0]
        transportistas = list(gr.triples((content, ECSDI.Nombre, None)))[0]
        fecha = gr.value(subject=content, predicate=ECSDI.Fecha)

        graph = Graph()

        graph_aux = Graph()
        graph_aux.bind('foaf', FOAF)
        graph_aux.bind('dso', DSO)
        graph_aux.bind("default", ECSDI)

        item = ECSDI['Devolucion-' + str(uuid.uuid4())]

        graph_aux.add((item, RDF.type, ECSDI.Devolucion))
        graph_aux.add((item, ECSDI.Factura, factura))
        graph_aux.add((item, ECSDI.Usuario, usuario))
        graph_aux.add((item, ECSDI.Producto, producto))
        graph_aux.add((item, ECSDI.Transportista, transportistas))
        graph_aux.add((item, ECSDI.Fecha, fecha))

        devos += graph_aux

        devos.serialize(destination=db.DBDevoluciones, format='turtle')
        logger.info("Petición de Envio realizada")

    except Exception as e:
        print(e)
        logger.info("No ha sido posible enviar la petición de envio")


def procesarDevolucion(content, gm):
    global VendedorAgent
    global GestorDevolucionesAgent
    global GestorEnviosAgent
    global mss_cnt

    logger.info("Procesando Devolucion")

    gr = Graph()
    gr.bind("default", ECSDI)
    agents.print_graph(gm)

    ontologyFile = open(db.DBDevoluciones)
    devos = Graph()
    devos.parse(ontologyFile, format='turtle')

    reg_obj = ECSDI['RespuestaDevolucion-' + str(uuid.uuid4())]
    gr.add((reg_obj, RDF.type, ECSDI.RespuestaDevolucion))

    usuario = gm.value(subject=content, predicate=ECSDI.Usuario)
    prod_suj = gm.value(subject=content, predicate=ECSDI.Producto)
    precio = gm.value(subject=prod_suj, predicate=ECSDI.Precio)
    peso = gm.value(subject=prod_suj, predicate=ECSDI.Peso )
    externo = gm.value(subject=prod_suj, predicate=ECSDI.Externo )
    motivo = str(gm.value(subject=content, predicate=ECSDI.Motivo))
    factura_suj = gm.value(subject=content, predicate=ECSDI.Factura)
    ciudad = gm.value(subject=factura_suj, predicate=ECSDI.Ciudad)
    tarjeta = gm.value(subject=factura_suj, predicate=ECSDI.Tarjeta)
    fecha = str(gm.value(subject=factura_suj, predicate=ECSDI.Fecha)).split('-')
    fecha = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
    hoy = datetime.date.today()
    if motivo == 'expectativa':
        plazoMax = fecha + datetime.timedelta(days=15)
        if hoy > plazoMax:
            logger.info("Devolucion rechazada por plazo máximo")
            gr.add((reg_obj, ECSDI.Estado, Literal('Rechazada', datatype=XSD.string)))
            return gr


    devo = list(devos.triples((None, ECSDI.Factura, factura_suj)))

    if len(devo) > 0:
        if len(list(devos.triples((devo, ECSDI.Producto, None)))) > 0:
            logger.info("Devolucion ya realizada previamente")
            gr.add((reg_obj, ECSDI.Estado, Literal('Duplicada', datatype=XSD.string)))
            return gr

    graph_message = Graph()
    graph_message.bind('foaf', FOAF)
    graph_message.bind('dso', DSO)
    graph_message.bind("default", ECSDI)
    reg_obj = ECSDI['EnvioCompra' + str(uuid.uuid4())]
    graph_message.add((reg_obj, RDF.type, ECSDI.EnvioDevolucion))
    graph_message.add((reg_obj, ECSDI.Ciudad, Literal(ciudad, datatype=XSD.string)))
    sujetoProductos = ECSDI['ProductosAdquiridos' + str(uuid.uuid4())]
    graph_message.add((sujetoProductos, RDF.type, ECSDI.ProductosAdquiridos))


    graph_message.add((prod_suj, ECSDI.Peso, Literal(float(peso), datatype=XSD.float)))
    graph_message.add((prod_suj, ECSDI.Externo, Literal(str(externo), datatype=XSD.string)))
    graph_message.add((sujetoProductos, ECSDI.Productos, URIRef(prod_suj)))

    graph_message.add((reg_obj, ECSDI.Contiene, URIRef(sujetoProductos)))
    graph_message.add((reg_obj, ECSDI.Prioridad, Literal(3, datatype=XSD.int)))

    graph_tes = Graph()
    graph_tes.bind('foaf', FOAF)
    graph_tes.bind('dso', DSO)
    graph_tes.bind("default", ECSDI)
    item = ECSDI['PagarCompra-' + str(uuid.uuid4())]
    graph_tes.add((item, RDF.type, ECSDI.PagarCompra))
    graph_tes.add((item, ECSDI.Tarjeta, tarjeta))
    graph_tes.add((item, ECSDI.Precio, Literal(precio, datatype=XSD.float)))
    graph_tes.add((item, ECSDI.Usuario, usuario))
    graph_tes.add((item, ECSDI.Contiene, factura_suj))
    graph_tes.add((prod_suj, ECSDI.Peso, Literal(float(peso), datatype=XSD.float)))
    graph_tes.add((prod_suj, ECSDI.Externo, Literal(str(externo), datatype=XSD.string)))
    graph_tes.add((factura_suj, ECSDI.Productos, URIRef(prod_suj)))


    thread = threading.Thread(target=pedirReintegro, args=(graph_tes, item))
    thread.start()


    thread = Thread(target=solicitarEnvio(), args=(graph_message, reg_obj, factura_suj, prod_suj, usuario), )
    thread.start()

    return gr
    
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
            Graph(), ACL['not-understood'], sender=GestorDevolucionesAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=GestorDevolucionesAgent.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            logger.info("Previo al if content")
            if 'content' in msgdic:
                response = Graph()
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

                if accion == ECSDI.PeticionDevolucion: #AÑADIR EN LA ONTOLOGIA
                    logger.info("Accion correcta")

                    for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                        gm.remove((item, None, None))

                    response = procesarDevolucion(content, gm) #retornamos la fecha y el transportista

                gr = build_message(response,
                               ACL['inform'],
                               sender=GestorDevolucionesAgent.uri,
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
    reg_obj = agn[GestorDevolucionesAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, GestorDevolucionesAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(GestorDevolucionesAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(GestorDevolucionesAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.GestorDevolucionesAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=GestorDevolucionesAgent.uri,
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
    global CentrosLogisticosAgents
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