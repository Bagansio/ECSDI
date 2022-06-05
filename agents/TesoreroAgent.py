# -*- coding: utf-8 -*-
"""
filename: MostradorAgent
Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH
Agente que se registra como agente de busquedas
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
    port = agents.agent_ports['TesoreroAgent']
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
TesoreroAgent = Agent('TesoreroAgent',
                                   agn.TesoreroAgent,
                                   'http://%s:%d/comm' % (hostaddr, port),
                                   'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))


GestorServicioExternoAgent = None
GestorProductosAgent = None

# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()


def pagarCompra(content, gm):    
    global GestorServicioExternoAgent
    global TesoreroAgent
    global DirectoryAgent
    global mss_cnt

    logger.info("Efectuando cobro")


    tarjeta = gm.value(subject=content, predicate=ECSDI.Tarjeta)
    #print(str(tarjeta))
    precio = gm.value(subject=content, predicate=ECSDI.Precio)
    #print(str(precio))
    compra = gm.value(subject=content, predicate=ECSDI.Contiene)
    
    usuarioNombre = gm.value(subject=content, predicate=ECSDI.Usuario)
    """ Cuando no se esta haciendo el juego de prueba hacer esto:"""
    #usuario = gm.value(subject=content, predicate=ECSDI.Usuario)
    #usuarioNombre = gm.value(subject=usuario, predicate=ECSDI.Nombre)

    grafoVendedores = Graph()
    try:
        if GestorServicioExternoAgent is None:
                logger.info("Obtiendo el agente Gestor Servicio Externo")
                GestorServicioExternoAgent = agents.get_agent(DSO.GestorServicioExternoAgent, TesoreroAgent, DirectoryAgent, mss_cnt)

        logger.info("Cobrando al usuario " +str(usuarioNombre)+ " con la tarjeta acabada en " +str(tarjeta[-4:])+ " un total de " +str(precio)+"€ por los productos" )

        graph_message = Graph()
        graph_message.bind('foaf', FOAF)
        graph_message.bind('dso', DSO)
        graph_message.bind("default", ECSDI)

        reg_obj = ECSDI['ObtenerVendedores' + str(mss_cnt)]
        graph_message.add((reg_obj, RDF.type, ECSDI.ObtenerVendedores))

        # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
        grafoVendedores = send_message(
            build_message(graph_message, perf=ACL.request,
                        sender=TesoreroAgent.uri,
                        receiver=GestorServicioExternoAgent.uri,
                        content=reg_obj,
                        msgcnt=mss_cnt),
            GestorServicioExternoAgent.address)

        mss_cnt += 1

    except Exception as e:
        print(e)
        logger.info("No ha sido posible obtener el agente y no se ha efectuado ningún cobro")
        return Graph()

    
    for producto in gm.objects(subject=compra, predicate=ECSDI.Productos):
        
        externo = str(gm.value(subject=producto, predicate=ECSDI.Externo))
        if externo != 'None':
            query = """
                prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                prefix xsd:<http://www.w3.org/2001/XMLSchema#>
                prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
                prefix owl:<http://www.w3.org/2002/07/owl#>
                SELECT ?servicioexterno ?nombre ?tarjeta
                    where {
                    {?servicioexterno rdf:type default:ServicioExterno } .
                    ?servicioexterno default:Nombre ?nombre .
                    ?servicioexterno default:Tarjeta ?tarjeta .

                    FILTER("""

            query += """?nombre = '""" + externo +"""'"""
            query += """)}""" 

            graph_query = grafoVendedores.query(query)


            for vendedor in graph_query:
                tarjeta = vendedor['tarjeta']
                logger.info("Pagando al vendedor externo " + vendedor['nombre'] + " con tarjeta acabada en " + tarjeta[-4:])

    logger.info("Cobro finalizado")

    return Graph()



def retornarImporte(content, gm):
    global GestorServicioExternoAgent
    global TesoreroAgent
    global DirectoryAgent
    global mss_cnt


    tarjeta = gm.value(subject=content, predicate=ECSDI.Tarjeta)
    precio = gm.value(subject=content, predicate=ECSDI.Precio)
    producto = gm.value(subject=content, predicate=ECSDI.Producto)
    usuarioNombre = gm.value(subject=content, predicate=ECSDI.Usuario)

    logger.info("Efectuando devolución")

    externo = gm.value(subject=producto, predicate=ECSDI.Externo)


    if externo is not None and externo != 'None':
        try:
            if GestorServicioExternoAgent is None:
                logger.info("Obtiendo el agente Gestor Servicio Externo")
                GestorServicioExternoAgent = agents.get_agent(DSO.GestorServicioExternoAgent, TesoreroAgent, DirectoryAgent, mss_cnt)
            logger.info("Pidiendole " +str(precio)+"€ al vendedor externo " +str(externo)+  " con la tarjeta acabada en " +str(tarjeta[-4:])+ " por el reembolso del producto.")


            graph_message = Graph()
            graph_message.bind('foaf', FOAF)
            graph_message.bind('dso', DSO)
            graph_message.bind("default", ECSDI)

            reg_obj = ECSDI['ObtenerVendedores' + str(mss_cnt)]
            graph_message.add((reg_obj, RDF.type, ECSDI.ObtenerVendedores))

            # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
            grafoVendedores = send_message(
                build_message(graph_message, perf=ACL.request,
                            sender=TesoreroAgent.uri,
                            receiver=GestorServicioExternoAgent.uri,
                            content=reg_obj,
                            msgcnt=mss_cnt),
                GestorServicioExternoAgent.address)

            mss_cnt += 1

        except Exception as e:
            print(e)
            logger.info("No ha sido posible obtener el agente y no se ha efectuado ningún cobro")
            return Graph()

    logger.info("Reembolsando el dinero del producto devuelto al usuario " +str(usuarioNombre)+ " con la tarjeta acabada en " +str(tarjeta[-4:])+ " un total de " +str(precio)+"€" )

    return Graph()







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
    reg_obj = agn[TesoreroAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, TesoreroAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(TesoreroAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(TesoreroAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.TesoreroAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=TesoreroAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr

def prueba():
    """No me deletees porfa gracias"""
    global GestorProductosAgent
    global mss_cnt
    gm = Graph()
    gm.bind("default", ECSDI)
    id = 0

    content = agn['PagarCompra' + str(id)]
    tarjeta = 123456789
    precio = 100.0
    usuarioNombre = "Álex"
    gm.add((content, RDF.type, ECSDI.PagarCompra))
    gm.add((content, ECSDI.Tarjeta, Literal(int(tarjeta), datatype=XSD.int)))
    #print(str(gm.value(subject=content, predicate=ECSDI.Tarjeta)))
    gm.add((content, ECSDI.Precio,  Literal(float(precio), datatype=XSD.float)))
    #print(str(gm.value(subject=content, predicate=ECSDI.Precio)))
    gm.add((content, ECSDI.Nombre, Literal(usuarioNombre, datatype=XSD.string)))


    if GestorProductosAgent is None:
        GestorProductosAgent = agents.get_agent(DSO.GestorProductosAgent, TesoreroAgent, DirectoryAgent, mss_cnt)

    graph_message = Graph()
    graph_message.bind('foaf', FOAF)
    graph_message.bind('dso', DSO)
    graph_message.bind("default", ECSDI)
    reg_obj = ECSDI['PeticionProductos' + str(mss_cnt)]
    graph_message.add((reg_obj, RDF.type, ECSDI.PeticionProductos))

        # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    graph = send_message(
        build_message(graph_message, perf=ACL.request,
                      sender=TesoreroAgent.uri,
                      receiver=GestorProductosAgent.uri,
                        content=reg_obj,
                        msgcnt=mss_cnt),
        GestorProductosAgent.address)

    mss_cnt += 1


    query = """
    prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    prefix xsd:<http://www.w3.org/2001/XMLSchema#>
    prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
    prefix owl:<http://www.w3.org/2002/07/owl#>
    SELECT ?producto ?externo
        where {
        {?producto rdf:type default:Producto } .
        ?producto default:Externo ?externo .
        }
        """
    
    graph_query = graph.query(query)

    sujetoProductos = ECSDI['ProductosPago' + str(id)] #sujetoCompra
    graph_message.add((sujetoProductos, RDF.type, ECSDI.ProductosPago))


    for producto in graph_query:
        product_externo = producto['externo']
        product_suj = producto['producto']

        gm.add((product_suj, ECSDI.Externo, Literal(product_externo, datatype=XSD.string)))
        gm.add((sujetoProductos, ECSDI.Productos, URIRef(product_suj))) #sujetoCompra

    gm.add((content, ECSDI.Contiene, URIRef(sujetoProductos)))  #ECSDI.DE

    pagarCompra(content, gm)


def prueba2():
    """No me deletees porfa gracias"""
    global GestorProductosAgent
    global mss_cnt
    gm = Graph()
    gm.bind("default", ECSDI)
    id = 0

    content = agn['RetornarImporte' + str(id)]
    tarjeta = 123456789
    precio = 100.0
    usuarioNombre = "Álex"
    gm.add((content, RDF.type, ECSDI.RetornarImporte))
    gm.add((content, ECSDI.Tarjeta, Literal(int(tarjeta), datatype=XSD.int)))
    #print(str(gm.value(subject=content, predicate=ECSDI.Tarjeta)))
    gm.add((content, ECSDI.Precio,  Literal(float(precio), datatype=XSD.float)))
    #print(str(gm.value(subject=content, predicate=ECSDI.Precio)))
    gm.add((content, ECSDI.Nombre, Literal(usuarioNombre, datatype=XSD.string)))


    if GestorProductosAgent is None:
        GestorProductosAgent = agents.get_agent(DSO.GestorProductosAgent, TesoreroAgent, DirectoryAgent, mss_cnt)

    graph_message = Graph()
    graph_message.bind('foaf', FOAF)
    graph_message.bind('dso', DSO)
    graph_message.bind("default", ECSDI)
    reg_obj = ECSDI['PeticionProductos' + str(mss_cnt)]
    graph_message.add((reg_obj, RDF.type, ECSDI.PeticionProductos))

        # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    graph = send_message(
        build_message(graph_message, perf=ACL.request,
                      sender=TesoreroAgent.uri,
                      receiver=GestorProductosAgent.uri,
                        content=reg_obj,
                        msgcnt=mss_cnt),
        GestorProductosAgent.address)

    mss_cnt += 1


    query = """
    prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    prefix xsd:<http://www.w3.org/2001/XMLSchema#>
    prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
    prefix owl:<http://www.w3.org/2002/07/owl#>
    SELECT ?producto ?externo
        where {
        {?producto rdf:type default:Producto } .
        ?producto default:Externo ?externo .
        }
        """
    
    graph_query = graph.query(query)
    xd = 0
    for producto in graph_query:
        if xd == 2:
            product_externo = producto['externo']
            product_suj = producto['producto']
            gm.add((product_suj, ECSDI.Externo, Literal(product_externo, datatype=XSD.string)))
            gm.add((content, ECSDI.Producto, URIRef(product_suj))) #sujetoCompra
            break
        xd = xd + 1
        


    retornarImporte(content, gm)




@app.route("/stop")
def stop():
    """
    Entrypoint que para el agente
    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"

@app.route("/iface")
def iface():
    """
    Entrypoint que para el agente
    :return:
    """
    prueba()

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
            Graph(), ACL['not-understood'], sender=TesoreroAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=TesoreroAgent.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro
            result = Graph()
            # Averiguamos el tipo de la accion
            if 'content' in msgdic:

                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

                for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                    gm.remove((item, None, None))

                if accion == ECSDI.PagarCompra:
                    result = pagarCompra(content, gm)
                elif accion == ECSDI.RetornarImporte:
                    result = retornarImporte(content, gm)

            # Aqui realizariamos lo que pide la accion
            # Por ahora simplemente retornamos un Inform-done
            gr = build_message(result,
                               ACL['inform'],
                               sender=TesoreroAgent.uri,
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