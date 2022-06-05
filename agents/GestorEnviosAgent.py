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



__author__ = 'Artur, Cristian, Bagansio'

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
    hostaddr = "192.168.18.10"
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



CentrosLogisticosAgents = None
GestorServicioExternoAgent = None


# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()


def crearGrafo(content, gm, reg_obj):
    grafo = Graph()
    grafo.bind('foaf', FOAF)
    grafo.bind('dso', DSO)
    grafo.bind("default", ECSDI)
    grafo.add((reg_obj, RDF.type, ECSDI.PrepararEnvio))

    prioridad = gm.value(subject=content, predicate=ECSDI.Prioridad)
    grafo.add((reg_obj, ECSDI.Prioridad, Literal(prioridad, datatype=XSD.int)))

    return grafo

def solicitarDevolucion(content, gm):
    return None


def solicitarEnvio(content, gm):
    global CentrosLogisticosAgents
    global GestorServicioExternoAgent
    global mss_cnt


    propio = True
    if CentrosLogisticosAgents is None:
        CentrosLogisticosAgents = obtenerCentrosLogiticos()

    logger.info("SolicitarEnvio")
    
    ciudad = gm.value(subject=content, predicate=ECSDI.Ciudad)
    

    centrosMasCercanos = centrosMasProximos(str(ciudad))

    

    centrosLogisticos = obtenerCentrosLogiticos()

    
    compra = gm.value(subject=content, predicate = ECSDI.Contiene) 
    

    if GestorServicioExternoAgent is None:
        logger.info('Buscando al agente GestorServicioExternoAgent')
        GestorServicioExternoAgent = agents.get_agent(DSO.GestorServicioExternoAgent, GestorEnviosAgent, DirectoryAgent, mss_cnt)
            
    graph_message = Graph()
    graph_message.bind('foaf', FOAF)
    graph_message.bind('dso', DSO)
    graph_message.bind("default", ECSDI)
    reg_obj = ECSDI['ObtenerVendedores' + str(mss_cnt)]
    graph_message.add((reg_obj, RDF.type, ECSDI.ObtenerVendedores))

        # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    grafoVendedores = send_message(
        build_message(graph_message, perf=ACL.request,
                    sender=GestorEnviosAgent.uri,
                    receiver=GestorServicioExternoAgent.uri,
                        content=reg_obj,
                        msgcnt=mss_cnt),
        GestorServicioExternoAgent.address)

    mss_cnt += 1

    reg_obj1 = ECSDI['PrepararEnvio' + str(uuid.uuid4())]

    prioridad = int(gm.value(subject=content, predicate=ECSDI.Prioridad))

    grafo1 = crearGrafo(content,gm, reg_obj1)

    reg_obj2 = ECSDI['PrepararEnvio' + str(uuid.uuid4())]
    grafo2 = crearGrafo(content,gm, reg_obj2)

    reg_obj3 = ECSDI['PrepararEnvio' + str(uuid.uuid4())]
    grafo3 = crearGrafo(content,gm, reg_obj3)



    productosCentroLogistico = {
        "CentroLogisticoAgent1" : [grafo1, reg_obj1, False],
        "CentroLogisticoAgent2" : [grafo2, reg_obj2, False],
        "CentroLogisticoAgent3" : [grafo3, reg_obj3, False]
    }


    for producto in gm.objects(subject=compra, predicate=ECSDI.Productos):
        TransportePropio = False
        logger.info("producto: " + str(producto))

        externo = gm.value(subject=producto, predicate=ECSDI.Externo)

        if externo is not None and str(externo) != 'None':
            query = """
                prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                prefix xsd:<http://www.w3.org/2001/XMLSchema#>
                prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
                prefix owl:<http://www.w3.org/2002/07/owl#>
                SELECT ?servicioexterno ?nombre ?transportepropio
                    where {
                    {?servicioexterno rdf:type default:ServicioExterno } .
                    ?servicioexterno default:Nombre ?nombre .
                    ?servicioexterno default:TransportePropio ?transportepropio .

                    FILTER("""

            query += """?nombre = '""" + externo +"""'"""
            query += """)}""" 

            graph_query = grafoVendedores.query(query)
            #logger.info("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
            for vendedor in graph_query:
             #   logger.info("Comprobando el transporte propio del vendedor:" + str(vendedor) +"con transporte propio: " + str(vendedor['transportepropio']))
                if str(vendedor['transportepropio']) == 'true':
             #       logger.info("SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE SOYTRUE ")
                    TransportePropio = True

            #logger.info("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        
        if TransportePropio is False:
            propio = False
            Contiene = False
            print ('Producto1: ' + str(producto))
            for centro in centrosMasCercanos:
                #logger.info("CENTRO: " + centro)

                cent = centrosLogisticos[str(centro)]
                productos = cent['almacena']


                for p in productos:
                    if producto == p:
                        #logger.info("p = "+ str(p) + "producto = " + str(producto))

                        Contiene = True
                        break
                
                if Contiene is True:
                    reg_objAUX = productosCentroLogistico[str(centro)][1]
                    peso = gm.value(subject=producto, predicate=ECSDI.Peso)

                    productosCentroLogistico[str(centro)][0].add((reg_objAUX, ECSDI.Lote, URIRef(producto)))
                    productosCentroLogistico[str(centro)][0].add((producto, ECSDI.Peso, Literal(float(peso), datatype=XSD.float)))
                    productosCentroLogistico[str(centro)][2]=True

                    break
                
    precio_transporte = 0.
    date = None
    transportistas = set()
    for key,centro in productosCentroLogistico.items():

        logger.info("COMPROBANDO EL CENTRO: " +str(key))

        if centro[2] is True:
            logger.info("Enviado productos lote")
            logger.info("EL CENTRO ES:" +str(key))

            
            
            logger.info("CONTENT= " +centro[1])
            
            

                # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
            grafoVendedores = send_message(
                build_message(centro[0], perf=ACL.request,
                            sender=GestorEnviosAgent.uri,
                            receiver=CentrosLogisticosAgents[key]['uri'],
                            content=centro[1],
                            msgcnt=mss_cnt),
                CentrosLogisticosAgents[key]['address'])

            mss_cnt += 1        
            
            content = list(grafoVendedores.triples((None, ECSDI.Precio, None)))[0][0]

            precio_transporte += float(grafoVendedores.value(subject=content, predicate=ECSDI.Precio))
            transportistas.add(str(grafoVendedores.value(subject=content, predicate=ECSDI.Nombre)))
            fecha = str(grafoVendedores.value(subject=content, predicate=ECSDI.Fecha)).split('-')
            fecha = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
            if date is None:
                date = fecha
            elif fecha > date:
                date = fecha

    gr = Graph()
    gr.bind('foaf', FOAF)
    gr.bind('dso', DSO)
    gr.bind("default", ECSDI)
    reg_obj = ECSDI['RespuestaEnvio' + str(mss_cnt)]
    gr.add((reg_obj, RDF.type, ECSDI.RespuestaEnvio))
    gr.add((reg_obj, ECSDI.Precio, Literal(precio_transporte, datatype=XSD.float)))

    if propio:
        gr.add((reg_obj, ECSDI.Fecha, Literal(str(agents.get_date(prioridad)), datatype=XSD.date)))
        gr.add((reg_obj, ECSDI.Nombre, Literal('Propio', datatype=XSD.string)))
    else:
        gr.add((reg_obj, ECSDI.Fecha, Literal(date, datatype=XSD.date)))
        for transporte in transportistas:
            gr.add((reg_obj, ECSDI.Nombre, Literal(transporte, datatype=XSD.string)))

    return gr






def obtenerCentrosLogiticos():
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


    centros = dict()
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

    query_result = resultado.query(query)

    for centro in query_result:
        cen = dict()

        cen['posicionx'] = float(centro['posicionx'])
        cen['posiciony'] = float(centro['posiciony'])
        cen['almacena'] = list(resultado.objects(subject=centro['centrologistico'], predicate=ECSDI.Almacena))

        cen['uri'] = agn[centro['nombre']]
        cen['address'] = gr.value(predicate=DSO.Address, subject=cen['uri'])
        centros[str(centro['nombre'])] = cen

    return centros



    
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
                        response = solicitarEnvio(content, gm) #retornamos la fecha y el transportista


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
    global CentrosLogisticosAgents
    # Registramos el agente
    gr = register_message()

    CentrosLogisticosAgents = obtenerCentrosLogiticos()
    


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