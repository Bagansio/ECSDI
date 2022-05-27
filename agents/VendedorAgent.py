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
    port = agents.agent_ports['VendedorAgent']
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
VendedorAgent = Agent('VendedorAgent',
                                   agn.VendedorAgent,
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

def RegistrarVenta(gm):
    logger.info('Registrando la venta')
    ontologyFile = open(db.DBCompras)

    grafoVentas = Graph()
    grafoVentas.bind('default', ECSDI)
    grafoVentas.parse(ontologyFile, format='turtle')
    grafoVentas += gm

    grafoVentas.serialize(destination=db.DBCompras, format='turtle')
    logger.info("Registro de venta finalizado")


def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt


def enviarVenta(content, gm):
    logger.info('Haciendo petición de envio TODAVIA NO IMPLEMENTADA!!')
    gm.remove((content, RDF.type, ECSDI.PeticionCompra))
    sujeto = ECSDI['PeticionEnvio' + str(getMessageCount())]
    gm.add((sujeto, RDF.type, ECSDI.PeticionEnvio)) #No se si esta peticionenvio


    for a,b,c in gm:
        if a == content:
            gm.remove((a, b, c))
            gm.add((sujeto, b, c))

    logger.info("Petición de envio enviada")
    #                                >No se si se llamara asi XD<
    EnviadorAgent = agents.get_agent(DSO.EnviadorAgent, VendedorAgent, DirectoryAgent, mss_cnt)
    
    #Acabar esto cuando este el agente enviador
    """
    rc = send_message(build_message(gm,
                                    perf=ACL.request, sender=VendedorAgent.uri,
                                    receiver=enviador.uri,
                                    msgcnt=getMessageCount(), content=sujeto), enviador.address)
    """


    

def vender(content, gm):
    logger.info('Petición de compra recibida')
    thread = threading.Thread(target=RegistrarVenta, args=(gm,))
    thread.start()

    tarjetaCredito = gm.value(subject=content, predicate=ECSDI.Tarjeta) #AÑADIR TARJETA A LA ONTOLOGIA

    #Creamos la factura  
    grafoFactura = Graph()
    grafoFactura.bind('default', ECSDI)
    logger.info("Creando la factura")
    sujeto = ECSDI['Factura' + str(getMessageCount())]
    grafoFactura.add((sujeto, RDF.type, ECSDI.Factura))#NO SE SI HAY FACTURA EN LA ONTO
    grafoFactura.add((sujeto, ECSDI.Tarjeta, Literal(tarjetaCredito, datatype=XSD.int)))

    compra = gm.value(subject=content, predicate=ECSDI.De) #ESTO EXISTE EL ECSDI.De??? XDDD

    precio = 0
    for producto in gm.objects(subject=compra, predicate=ECSDI.Contiene):
        #añadimos producto
        grafoFactura.add((producto, RDF.type, ECSDI.Producto)) 

        #añadimos nombre producto
        NProducto = gm.value(subject=producto, predicate=ECSDI.Nombre)
        grafoFactura.add((producto, ECSDI.Nombre, Literal(NProducto, datatype=XSD.string)))

        #añadimos precio producto
        p = gm.value(subject=producto, predicate=ECSDI.Precio)
        grafoFactura.add((producto, ECSDI.Precio, Literal(float(p), datatype=XSD.float)))

        #sumamos a precio total
        precio += float(p)

        grafoFactura.add((sujeto, ECSDI.FormadaPor, URIRef(producto)))

    grafoFactura.add((sujeto, ECSDI.PrecioTotal, Literal(precio, datatype=XSD.float))) #Revisar si hay preciototal en la onto
    s = gm.value(predicate=RDF.type, object=ECSDI.PeticionCompra)

    gm.add((s, ECSDI.PrecioTotal, Literal(precio, datatype=XSD.float)))

    #IMPLEMENTAR ENVIAR VENTA (FALTAN LOS AGENTES ENVIADORES)
    thread = Thread(target=enviarVenta, args=(content, gm))
    thread.start()

    logger.info("Retornando la factura")
    return grafoFactura














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
    reg_obj = agn[VendedorAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, VendedorAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(VendedorAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(VendedorAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.VendedorAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=VendedorAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

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
            Graph(), ACL['not-understood'], sender=VendedorAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=VendedorAgent.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

            if accion == ECSDI.PeticionCompra: #AÑADIR EN LA ONTOLOGIA

                # Eliminar los ACLMessage
                for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                    gm.remove((item, None, None))

                gr =  vender(gm, content) #retornamos la factura
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