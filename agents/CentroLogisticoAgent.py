# -*- coding: utf-8 -*-
"""
filename: CentroLogisticoAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que lleva un registro de otros agentes

Utiliza un registro simple que guarda en un grafo RDF

El registro no es persistente y se mantiene mientras el agente funciona

Las acciones que se pueden usar estan definidas en la ontología
directory-service-ontology.owl


@author: Bagansio, Artur Farriols, Cristian Mesa
"""
import threading
from pathlib import Path
import sys



path_root = Path(__file__).parents[1]
sys.path.append(str(path_root))

from multiprocessing import Process, Queue
import argparse
import logging
import datetime

from utils import agents
from flask import Flask, request, render_template
from rdflib import Graph, RDF, Namespace, RDFS, Literal, XSD
from rdflib.namespace import FOAF

from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.ACLMessages import build_message, get_message_properties, send_message
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Util import gethostname
from AgentUtil.OntoNamespaces import ECSDI
import socket

__author__ = 'Bagansio'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor est abierto al exterior o no", action='store_true',
                    default=False)
parser.add_argument('--verbose', help="Genera un log de la comunicacion del servidor web", action='store_true',
                    default=False)
parser.add_argument('--port', type=int,
                    help="Puerto de comunicacion del agente")
parser.add_argument('--dhost', help="Host del agente de directorio")
parser.add_argument('--dport', type=int,
                    help="Puerto de comunicacion del agente de directorio")

parser.add_argument('--centro', type=int,
                    help="Id del Centro Logistico")


# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = agents.agent_ports['CentroLogisticoAgent']
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

# Directory Service Graph
dsgraph = Graph()

# Vinculamos todos los espacios de nombre a utilizar
dsgraph.bind('acl', ACL)
dsgraph.bind('rdf', RDF)
dsgraph.bind('rdfs', RDFS)
dsgraph.bind('foaf', FOAF)
dsgraph.bind('dso', DSO)

agn = Namespace("http://www.agentes.org#")

# Datos del Agente
CentroLogisticoAgent = Agent('CentroLogisticoAgent' + str(args.centro),
                       agn['CentroLogisticoAgent' + str(args.centro)],
                       'http://%s:%d/comm' % (hostaddr, port),
                       'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

app = Flask(__name__)

if not args.verbose:
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

mss_cnt = 0

cola1 = Queue()  # Cola de comunicacion entre procesos



def pedirContraOferta(agn_uri, agn_add, peso, precio, indx, contraOfertas, mss_cnt):
    gmess = Graph()
    # Construimos el mensaje de registro
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    gmess.bind("default", ECSDI)
    reg_obj = ECSDI['PedirOferta' + str(mss_cnt) ]
    gmess.add((reg_obj, RDF.type, ECSDI.PedirContraOferta))
    gmess.add((reg_obj, ECSDI.Peso, Literal(peso, datatype=XSD.float)))
    gmess.add((reg_obj, ECSDI.Precio, Literal(precio, datatype=XSD.float)))
    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=CentroLogisticoAgent.uri,
                      receiver=agn_uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        agn_add)

    mss_cnt += 1
    precioContra = list(gr.triples((None, ECSDI.Precio, None)))[0][2]

    contraOfertas[indx][1] = list(gr.triples((None, ECSDI.Nombre, None)))[0][2]
    if precioContra != -1 and precioContra < precio:
        contraOfertas[indx][0] = precioContra



def negociar(content, gm):

    global mss_cnt
    global dsgraph

    # Obtenemos los productos y calculamos el peso total
    peso = 0
    for producto in gm.objects(subject=content, predicate=ECSDI.Lote):
        # Obtenemos precio producto
        p = gm.value(subject=producto, predicate=ECSDI.Peso)

        # sumamos a precio total
        peso += float(p)

    # Obtenemos un transportista random para pedir oferta
    rsearch = list(dsgraph.triples((None, DSO.AgentType, DSO.TransportistaAgent)))
    agn_uri = rsearch[0][0]
    agn_add = dsgraph.value(subject=agn_uri, predicate=DSO.Address)

    gmess = Graph()
    # Construimos el mensaje de registro
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    gmess.bind("default", ECSDI)
    reg_obj = ECSDI['PedirOferta' + str(mss_cnt)]
    gmess.add((reg_obj, RDF.type,  ECSDI.PedirOferta))
    gmess.add((reg_obj, ECSDI.Peso, Literal(peso, datatype=XSD.float)))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=CentroLogisticoAgent.uri,
                      receiver=agn_uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        agn_add)
    mss_cnt += 1

    precioOferta = list(gr.triples((None, ECSDI.Precio, None)))[0][2]
    prioridad = list(gm.triples((None, ECSDI.Prioridad, None)))[0][2]

    contraOfertas = [[-1 for y in range(2)] for x in range(len(rsearch))]
    threads = []
    for indx, transportista in enumerate(rsearch):
        trans_uri = transportista[0]
        trans_add = dsgraph.value(subject=trans_uri, predicate=DSO.Address)

        if agn_uri != trans_uri:
            threads.append(
                threading.Thread(
                    target=pedirContraOferta,
                    args=(trans_uri, trans_add, peso, precioOferta, indx, contraOfertas, mss_cnt)))

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    transporte = list(gr.triples((None, ECSDI.Nombre, None)))[0][2]
    precioTransporte = precioOferta
    for contra in contraOfertas:
        if contra[0] != -1 and contra[0] < precioTransporte:
            precioTransporte = contra[0]
            transporte = contra[1]



    date = agents.get_date(int(prioridad))

    gr = Graph()
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    gmess.bind("default", ECSDI)
    reg_obj = ECSDI['RespuestaEnvio' + str(mss_cnt)]
    gmess.add((reg_obj, RDF.type, ECSDI.RespuestaEnvio))
    gmess.add((reg_obj, ECSDI.Precio, Literal(precioTransporte, datatype=XSD.float)))
    gmess.add((reg_obj, ECSDI.Nombre, Literal(transporte, datatype=XSD.string)))
    gmess.add((reg_obj, ECSDI.Fecha, Literal(date, datatype=XSD.date)))

    agents.print_graph(gmess)
    return gmess



@app.route("/Register")
def register():
    """
    Entry point del agente que recibe los mensajes de registro
    La respuesta es enviada al retornar la funcion,
    no hay necesidad de enviar el mensaje explicitamente

    Asumimos una version simplificada del protocolo FIPA-request
    en la que no enviamos el mesaje Agree cuando vamos a responder

    :return:
    """

    def process_register():
        # Si la hay extraemos el nombre del agente (FOAF.name), el URI del agente
        # su direccion y su tipo

        logger.info('Peticion de registro')

        agn_add = gm.value(subject=content, predicate=DSO.Address)
        agn_name = gm.value(subject=content, predicate=FOAF.name)
        agn_uri = gm.value(subject=content, predicate=DSO.Uri)
        agn_type = gm.value(subject=content, predicate=DSO.AgentType)

        # Añadimos la informacion en el grafo de registro vinculandola a la URI
        # del agente y registrandola como tipo FOAF.Agent
        dsgraph.add((agn_uri, RDF.type, FOAF.Agent))
        dsgraph.add((agn_uri, FOAF.name, agn_name))
        dsgraph.add((agn_uri, DSO.Address, agn_add))
        dsgraph.add((agn_uri, DSO.AgentType, agn_type))

        # Generamos un mensaje de respuesta
        return build_message(Graph(),
                             ACL.confirm,
                             sender=DirectoryAgent.uri,
                             receiver=agn_uri,
                             msgcnt=mss_cnt)

    def process_search():
        # Asumimos que hay una accion de busqueda que puede tener
        # diferentes parametros en funcion de si se busca un tipo de agente
        # o un agente concreto por URI o nombre
        # Podriamos resolver esto tambien con un query-ref y enviar un objeto de
        # registro con variables y constantes

        # Solo consideramos cuando Search indica el tipo de agente
        # Buscamos una coincidencia exacta
        # Retornamos el primero de la lista de posibilidades

        logger.info('Peticion de busqueda')

        agn_type = gm.value(subject=content, predicate=DSO.AgentType)

        rsearch = dsgraph.triples(
                                (None,
                                 DSO.AgentType,
                                 agn_type))

        try:

            agn_uri = list(rsearch)[0][0]
            agn_add = dsgraph.value(subject=agn_uri, predicate=DSO.Address)

            gr = Graph()
            gr.bind('dso', DSO)
            rsp_obj = agn['Directory-response']
            gr.add((rsp_obj, DSO.Address, agn_add))
            gr.add((rsp_obj, DSO.Uri, agn_uri))
            return build_message(gr,
                                 ACL.inform,
                                 sender=DirectoryAgent.uri,
                                 msgcnt=mss_cnt,
                                 receiver=agn_uri,
                                 content=rsp_obj)
        except Exception as e:
            logger.info("No Hay ningun agente de ese tipo registrado")
            # Si no encontramos nada retornamos un inform sin contenido
            return build_message(Graph(),
                                 ACL.inform,
                                 sender=DirectoryAgent.uri,
                                 msgcnt=mss_cnt)

    global dsgraph
    global mss_cnt
    # Extraemos el mensaje y creamos un grafo con él
    message = request.args['content']
    gm = Graph()
    gm.parse(data=message, format='xml')

    msgdic = get_message_properties(gm)

    # Comprobamos que sea un mensaje FIPA ACL
    if not msgdic:
        # Si no es, respondemos que no hemos entendido el mensaje
        gr = build_message(Graph(),
                           ACL['not-understood'],
                           sender=DirectoryAgent.uri,
                           msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        if msgdic['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(Graph(),
                               ACL['not-understood'],
                               sender=DirectoryAgent.uri,
                               msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia
            # de registro
            content = msgdic['content']
            # Averiguamos el tipo de la accion
            accion = gm.value(subject=content, predicate=RDF.type)

            # Accion de registro
            if accion == DSO.Register:
                gr = process_register()
            # Accion de busqueda
            elif accion == DSO.Search:
                gr = process_search()

            # No habia ninguna accion en el mensaje
            else:
                gr = build_message(Graph(),
                                   ACL['not-understood'],
                                   sender=DirectoryAgent.uri,
                                   msgcnt=mss_cnt)
    mss_cnt += 1

    return gr.serialize(format='xml')


@app.route('/info')
def info():
    """
    Entrada que da informacion sobre el agente a traves de una pagina web
    """
    global dsgraph
    global mss_cnt

    gmess = Graph()
    # Construimos el mensaje de registro
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    gmess.bind("default", ECSDI)
    reg_obj = ECSDI['test' + str(mss_cnt)]
    test1 = ECSDI['prod1']
    test2 = ECSDI['prod1']
    gmess.add((reg_obj, RDF.type, ECSDI.test))
    gmess.add((reg_obj, ECSDI.Lote, test1))
    gmess.add((reg_obj, ECSDI.Lote, test2))
    gmess.add((test1, ECSDI.Peso, Literal(3, datatype=XSD.float)))
    gmess.add((test2, ECSDI.Peso, Literal(5, datatype=XSD.float)))
    gmess.add((reg_obj, ECSDI.Prioridad, Literal(1, datatype=XSD.int)))


    negociar(reg_obj, gmess)
    return render_template('info.html', nmess=mss_cnt, graph=dsgraph.serialize(format='turtle'))



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
            Graph(), ACL['not-understood'], sender=CentroLogisticoAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=CentroLogisticoAgent.uri, msgcnt=mss_cnt)
        else:
            # Extraemos el objeto del contenido que ha de ser una accion de la ontologia de acciones del agente
            # de registro

            # Averiguamos el tipo de la accion
            if 'content' in msgdic:
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)
                result = Graph()
                if accion == ECSDI.PrepararEnvio:

                    for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                        gm.remove((item, None, None))

                    result = negociar(content, gm)

            # Aqui realizariamos lo que pide la accion
            # Por ahora simplemente retornamos un Inform-done
            gr = build_message(result,
                               ACL['inform'],
                               sender=CentroLogisticoAgent.uri,
                               msgcnt=mss_cnt,
                               receiver=msgdic['sender'], )
    mss_cnt += 1

    logger.info('Respondemos a la peticion')

    return gr.serialize(format='xml')

@app.route("/stop")
def stop():
    """
    Entrada que para el agente
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    global cola1
    cola1.put(0)


def agentbehavior1(cola):
    """
    Behaviour que simplemente espera mensajes de una cola y los imprime
    hasta que llega un 0 a la cola
    """

    # Registramos el agente
    gr = register_message()

    fin = False
    while not fin:
        while cola.empty():
            pass
        v = cola.get()
        if v == 0:
            print(v)
            return 0
        else:
            print(v)


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
    reg_obj = agn[CentroLogisticoAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, CentroLogisticoAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(CentroLogisticoAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(CentroLogisticoAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.CentroLogisticoAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=CentroLogisticoAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr

if __name__ == '__main__':
    # Ponemos en marcha los behaviours como procesos
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor Flask
    app.run(host=hostname, port=port, debug=True)

    ab1.join()
    logger.info('The End')