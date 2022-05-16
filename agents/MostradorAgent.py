# -*- coding: utf-8 -*-
"""
filename: MostradorAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente de busquedas

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
    port = agents.agent_ports['MostradorAgent']
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
MostradorAgent = Agent('MostradorAgent',
                                   agn.MostradorAgent,
                                   'http://%s:%d/comm' % (hostaddr, port),
                                   'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

GestorProductosAgent = None


# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()

def buscarProductos(content, grafoEntrada):
    logger.info("Petición de busqueda recibida")
    parametros = grafoEntrada.objects(content, ECSDI.RestringidaPor)

    filtros = {}
    for p in parametros:
            if grafoEntrada.value(subject=p, predicate=RDF.type) == ECSDI.RestriccionNombre:
                Nombre = grafoEntrada.value(subject=p, predicate=ECSDI.Nombre)
                filtros['nombre'] = Nombre
            elif grafoEntrada.value(subject=p, predicate=RDF.type) == ECSDI.RestriccionPrecio:
                PrecioMaximo = grafoEntrada.value(subject=p, predicate=ECSDI.PrecioMaximo)
                PrecioMinimo = grafoEntrada.value(subject=p, predicate=ECSDI.PrecioMinimo)
                filtros['precio_max'] = PrecioMaximo
                filtros['precio_min'] = PrecioMinimo
            elif grafoEntrada.value(subject=p, predicate=RDF.type) == ECSDI.RestriccionCategoria:
                Categoria = grafoEntrada.value(subject=p, predicate=ECSDI.Categoria)
                filtros['categoria'] = Categoria
            elif grafoEntrada.value(subject=p, predicate=RDF.type) == ECSDI.RestriccionMarca:
                Marca = grafoEntrada.value(subject=p, predicate=ECSDI.Marca)
                filtros['marca'] = Marca
            elif grafoEntrada.value(subject=p, predicate=RDF.type) == ECSDI.RestriccionValoracion:
                Valoracion = grafoEntrada.value(subject=p, predicate=ECSDI.Valoracion)
                filtros['valoracion'] = Valoracion

    resultado = filtrarProductos(**parametros)
    return resultado




def filtrarProductos(precio_min = 0.0, precio_max = sys.float_info.max, nombre = None, marca = None, categoria = None, valoracion = None):
    
    logger.info("Obteniendo la lista de los productos")
    
    """
    ontologyFile = open(db.DBProductos)
    graph = Graph()
    graph.parse(ontologyFile, format='turtle') 
    """

    #comunicacion agentes
    try:
        item = ECSDI['PeticionAgregarProducto'+ str(uuid.uuid4())]
        graph_message = Graph()
        graph_message.add((item, RDF.type, ECSDI.PeticionProductos))

        if GestorProductosAgent is None:
            GestorProductosAgent = agents.get_agent(DSO.GestorProductosAgent, MostradorAgent, DirectoryAgent, mss_cnt)

        graph = send_message(build_message(graph_message,
                                                            perf=ACL.request, sender=MostradorAgent.uri,
                                                            receiver=GestorProductosAgent.uri,
                                                            msgcnt=mss_cnt, content=item), GestorProductosAgent.address)
        mss_cnt += 1

    except Exception as e:
        print(e)
        logger.info("No ha sido posible obtener los productos")
        return Graph()

    
    

#Consulta base de datos
    logger.info("Aplicando filtros de búsqueda")

    query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?Producto ?Nombre ?Precio ?Marca ?Id ?Peso
        where {
        ?Producto rdf:type default:Producto .
        ?Producto default:Nombre ?Nombre .
        ?Producto default:Precio ?Precio .
        ?Producto default:Marca ?Marca .
        ?Producto default:Id ?Id .
        ?Producto default:Peso ?Peso .
        ?Producto default:Valoracion ?Valoracion .
        FILTER("""

    next = (precio_min != 0.0 or precio_max != sys.float_info.max or nombre is not None or marca is not None or categoria is not None or valoracion is not None)

#parametros aplicados
    if nombre is not None:
        query += """?Nombre = """ + nombre + """'"""

    if marca is not None:
        if next:
            query += """ && """
        query += """?Marca = """ + marca + """'"""

    if categoria is not None:
        if next:
            query += """ && """
        query += """?Categoria = """ + categoria + """'"""

    #¿modificable?
    if precio_min is not None:
        if next:
            query += """ && """
        query += """?Precio >= """ + str(precio_min) + """'"""

    #¿modificable?
    if precio_max is not None:
        if next:
            query += """ && """
        query += """?Precio <= """ + str(precio_max) + """'"""

    if valoracion is not None:
        if next:
            query += """ && """
        query += """?Valoracion <= """ + str(valoracion) + """'"""


    query += """)}"""
    
    graph_query = graph.query(query)
    products_graph = Graph()
    graph.bind("ECSDI", ECSDI) #posible cambio
    sujetoRespuesta = ECSDI['RespuestaDeBusqueda' + str(uuid.uuid4())]
    #mss_cnt += 1
    products_graph.add(sujetoRespuesta, RDF.type, ECSDI.RespuestaDeBusqueda)
    products_filter = Graph()

    for product in graph_query:
        product_nombre = product.Nombre
        product_marca = product.Marca
        product_categoria = product.Categoria
        product_peso = product.Peso
        product_precio = product.Precio
        product_valoracion = product.Valoracion
        sujetoProducto = product.Producto

        products_graph.add((sujetoProducto, RDF.type, ECSDI.Producto))
        products_graph.add((sujetoProducto, ECSDI.Nombre, Literal(product_nombre, datatype=XSD.string)))
        products_graph.add((sujetoProducto, ECSDI.Descripcion, Literal(product_marca, datatype=XSD.string)))
        products_graph.add((sujetoProducto, ECSDI.Descripcion, Literal(product_categoria, datatype=XSD.string)))
        products_graph.add((sujetoProducto, ECSDI.Peso, Literal(product_peso, datatype=XSD.float)))
        products_graph.add((sujetoProducto, ECSDI.Precio, Literal(product_precio, datatype=XSD.float)))
        products_graph.add((sujetoRespuesta, ECSDI.Valoracion, URIRef(product_valoracion)))
        products_graph.add((sujetoRespuesta, ECSDI.Muestra, URIRef(sujetoProducto)))
        


        sujetoFiltro = ECSDI['ProductoFiltrado' + str(uuid.uuid4())]
        products_filter.add((sujetoFiltro, RDF.type, ECSDI.Producto))
        products_filter.add((sujetoFiltro, ECSDI.Nombre, Literal(product_nombre, datatype=XSD.string)))
        products_filter.add((sujetoFiltro, ECSDI.Descripcion, Literal(product_categoria, datatype=XSD.string)))
        products_filter.add((sujetoFiltro, ECSDI.Descripcion, Literal(product_marca, datatype=XSD.string)))
        products_filter.add((sujetoFiltro, ECSDI.Precio, Literal(product_precio, datatype=XSD.float)))

    thread = Thread(target=almacenarHistorial, args=(products_filter,))
    thread.start()

    logger.info('Resultado petición de busqueda obtenido')
    return products_graph


    
def almacenarHistorial(products_filter):
    try:
        logger.info("Almacenando busqueda")

        ontologyFile = open(db.DBHistorial)
        graphHistorial = Graph()
        graphHistorial.parse(ontologyFile, format='turtle')
        graphHistorial.bind("default", ECSDI)
        graphHistorial += products_filter

        graphHistorial.serialize(destination=db.DBHistorial, format='turtle')
        logger.info('Almacenamiento de historial finalizado')
    except Exception as e:
        print(e)
        logger.info("No ha sido posible guardar el historial")




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
    reg_obj = agn[MostradorAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, MostradorAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(MostradorAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(MostradorAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.HotelsAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=MostradorAgent.uri,
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