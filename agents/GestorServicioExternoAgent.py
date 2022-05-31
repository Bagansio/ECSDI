# -*- coding: utf-8 -*-
"""
filename: GestorServicioExternoAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente de hoteles y espera peticiones

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

from flask import Flask, request,render_template, session
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

__author__ = 'Bagansio'

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
    port = agents.agent_ports['GestorServicioExternoAgent']
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
GestorServicioExternoAgent = Agent('GestorServicioExternoAgent',
                                   agn.GestorServicioExternoAgent,
                                   'http://%s:%d/comm' % (hostaddr, port),
                                   'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))


GestorProductosAgent = None
RegistroServicioExternoAgent = None


# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()



# Agent Utils


def agregarDBProducto(data):
    try:

        logger.info("Registrando producto: [" + data['Nombre'] + " " + data['Marca'] +
                    "] de " + data['Peso'] + "kg por " + data['Precio'] + "€")
        # añadir el producto
        global mss_cnt
        ontologyFile = open(db.DBProductos)
        graph = Graph()
        graph.parse(ontologyFile, format='turtle')
        graph.bind("default", ECSDI)
        item = ECSDI['PeticionAgregarProducto' + str(uuid.uuid4())]

        graph.add((item, RDF.type, ECSDI.PeticionAgregarProducto))
        graph.add((item, ECSDI.Nombre, Literal(data['Nombre'], datatype=XSD.string)))
        graph.add((item, ECSDI.Precio, Literal(data['Precio'], datatype=XSD.float)))
        graph.add((item, ECSDI.Categoria, Literal(data['Categoria'], datatype=XSD.string)))
        graph.add((item, ECSDI.Peso, Literal(data['Peso'], datatype=XSD.float)))
        graph.add((item, ECSDI.Marca, Literal(data['Marca'], datatype=XSD.string)))
        graph.add((item, ECSDI.Externo, Literal(data['Externo'], datatype=XSD.string)))

        global GestorProductosAgent

        if GestorProductosAgent is None:
            GestorProductosAgent = agents.get_agent(DSO.GestorProductosAgent, GestorServicioExternoAgent, DirectoryAgent, mss_cnt)

        resultadoComunicacion = send_message(build_message(graph,
                                                           perf=ACL.request, sender=GestorServicioExternoAgent.uri,
                                                           receiver=GestorProductosAgent.uri,
                                                           msgcnt=mss_cnt, content=item), GestorProductosAgent.address)

        mss_cnt += 1
        logger.info("Registro de nuevo producto finalizado")
        return resultadoComunicacion

    except Exception as e:
        print(e)
        logger.info("Registro de nuevo producto fallido")
    return Graph()

def procesarProductoExterno(graph):
    data = {
        'Categoria': None,
        'Marca': None,
        'Nombre': None,
        'Peso': None,
        'Precio': None,
    }

    for a,b,c in graph:
        if b == ECSDI.Categoria:
            data['Categoria'] = c

        elif b == ECSDI.Marca:
            data['Marca'] = c

        elif b == ECSDI.Nombre:
            data['Nombre'] = c

        elif b == ECSDI.Peso:
            data['Peso'] = c

        elif b == ECSDI.Precio:
            data['Precio'] = c


    return agregarDBProducto(data)

# Agrega un Producto Externo a la BD
def agregarproducto(content, gm):
    logger.info("Recibida peticion de añadir productos")
    for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
        gm.remove((item, None, None))

    thread = threading.Thread(target=procesarProductoExterno, args=(gm,))
    thread.start()

    resultadoComunicacion = Graph()

    return resultadoComunicacion

def agregarDBServicioExterno(data):
    try:
        logger.info('Registrando Servicio Externo: Nombre = ' + data['Nombre'] + ' TransportePropio = ' + data['TransportePropio'] + ' Tarjeta = ' + data['Tarjeta'])
        global mss_cnt
        ontologyFile = open(db.DBServicioExterno)
        graph = Graph()
        graph.parse(ontologyFile, format='turtle')
        graph.bind("default", ECSDI)
        id = str(uuid.uuid4())

        item = ECSDI['ServicioExterno'+id]

        graph.add((item, RDF.type, ECSDI.ServicioExterno))
        graph.add((item, ECSDI.Nombre, Literal(data['Nombre'], datatype=XSD.string)))
        graph.add((item, ECSDI.TransportePropio, Literal(data['TransportePropio'], datatype=XSD.boolean)))
        graph.add((item, ECSDI.Tarjeta, Literal(data['Tarjeta'], datatype=XSD.int)))

        graph.serialize(destination=db.DBServicioExterno, format='turtle')
        logger.info("Registro de nuevo servicio externo finalizado")

    except:
        logger.info("Registro de nuevo servicio externo fallido")

    
def procesarServicioExterno(content, gm):
    data = {
        'Nombre': None,
        'TransportePropio': None,
        'Tarjeta': None,
    }

    for a,b,c in gm:

        if 'Peticion' in a and b == ECSDI.Nombre:
            data['Nombre'] = c

        elif 'Peticion' in a and b == ECSDI.TransportePropio:
            data['TransportePropio'] = c

        elif 'Peticion' in a and  b == ECSDI.Tarjeta:
            data['Tarjeta'] = c

    agregarDBServicioExterno(data)


def agregarServicioExterno(content, gm):
    logger.info('Recibida petición de añadir servicio externo')
    for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
        gm.remove((item, None, None))

    thread = threading.Thread(target=procesarServicioExterno, args=(content, gm))
    thread.start()

    resultadoComunicacion = Graph()

    return resultadoComunicacion


def obtener_vendedores():
    print ("Start")
    ontologyFile = open(db.DBServicioExterno)
    grafoVendedores = Graph()
    grafoVendedores.parse(ontologyFile, format='turtle')
    print ("grafo obtenido")

    #for a,b,c in grafoVendedores:
        #print(a)
        #print(b)
        #print(c)

    query = """
    prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    prefix xsd:<http://www.w3.org/2001/XMLSchema#>
    prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
    prefix owl:<http://www.w3.org/2002/07/owl#>
    SELECT ?servicioexterno ?nombre 
        where {
        {?servicioexterno rdf:type default:ServicioExterno } .
        ?servicioexterno default:Nombre ?nombre .
        } """

    print ("query declarada")

    vendedoresInfo = grafoVendedores.query(query)

    print ("query ejecutada")
    
    print ("XXXXXXXXXXXXXXXXXXXXXXXXXXX")

    vendedores = []

    for vendedor in vendedoresInfo:
        #print (vendedor)
        print (vendedor['nombre'])
        print (vendedor['servicioexterno'])
        vendedores.append(str(vendedor['nombre']))

    print ("XXXXXXXXXXXXXXXXXXXXXXXXXXX")

    for vendedor in vendedores:
        print (vendedor)
    
    return vendedores

"""
def obtener_vendedores(form = None):
    global mss_cnt
    global RegistroServicioExternoAgent

    if RegistroServicioExternoAgent is None:
        logger.info('Buscando al agente Registro Servicio Externo')
        RegistroServicioExternoAgent = agents.get_agent(DSO.RegistroServicioExternoAgent, GestorServicioExternoAgent, DirectoryAgent, mss_cnt)
        mss_cnt += 1

    gmess = Graph()
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    gmess.bind("default", ECSDI)
    reg_obj = agn['BuscarAgentesExternos' + str(mss_cnt)]
    gmess.add((reg_obj, RDF.type, ECSDI.BuscarAgentesExternos))

    us = None
    if 'usuario' in session:
        us = session['usuario']

    gmess.add((reg_obj, ECSDI.Id, Literal(us, datatype=XSD.string)))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos

    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=GestorServicioExternoAgent.uri,
                      receiver=RegistroServicioExternoAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        RegistroServicioExternoAgent.address)
    mss_cnt += 1

    query = 
                prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                prefix xsd:<http://www.w3.org/2001/XMLSchema#>
                prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
                prefix owl:<http://www.w3.org/2002/07/owl#>
                SELECT ?servicioexterno ?nombre 
                    where {
                    {?servicioexterno rdf:type default:ServicioExterno } .
                    ?servicioexterno default:Nombre ?nombre .
                    }

    return gr.query(query) """


# Agent functions

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
    reg_obj = agn[GestorServicioExternoAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, GestorServicioExternoAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(GestorServicioExternoAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(GestorServicioExternoAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.GestorServicioExternoAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=GestorServicioExternoAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr


@app.route("/addproduct", methods=['GET', 'POST'])
def browser_iface():
    """
    Permite la comunicacion con el agente via un navegador
    via un formulario
    """

    """"
    graph_query = obtener_vendedores()
    
    vendedoresExternos = []

    for vendedor in graph_query:
        vendedoresExternos.append(vendedor) """

    

    form = request.form
    if 'message' in form:
        if form['Nombre'] != '' and form['Marca'] != '' and form['Precio'] != '' and\
           form['Categoria'] != '' and form['Peso'] != ''  and form['Descripcion'] != '' and form['Externo'] != '':

            agregarDBProducto(request.form)

        else:
            logger.info('Error añadiendo el producto externo, formulario incorrecto')


    vendedores = obtener_vendedores() 
    return render_template('agregarproductoexterno.html', vendedores=vendedores)

@app.route("/addvendedor", methods=['GET', 'POST'])
def browser_addvendedor():
    """
    Simplemente es para probar que funciona
    """

    form = request.form

    if 'message' in form:
        if form['Nombre'] != '' and form['TransportePropio'] != '' and form['Tarjeta'] != '':
            data = dict(form)

            agregarDBServicioExterno(data)

        else:
            logger.info('Error añadiendo el servicio externo, formulario incorrecto')


    return render_template('agregarservicioexterno.html')
    


@app.route("/stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


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
            Graph(), ACL['not-understood'], sender=GestorServicioExternoAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=GestorServicioExternoAgent.uri, msgcnt=mss_cnt)
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
                               sender=GestorServicioExternoAgent.uri,
                               msgcnt=mss_cnt,
                               receiver=msgdic['sender'], )
    mss_cnt += 1

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')


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
