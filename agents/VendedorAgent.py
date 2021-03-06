# -*- coding: utf-8 -*-
"""
filename: MostradorAgent
Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

A este agente hay que pasarle un grafo con:
    numTarjeta 
    prioridad 
    direccion 
    Ciudad 
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

GestorProductosAgent = None
GestorEnviosAgent = None
TesoreroAgent = None


# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()

def RegistrarVenta(grafoFactura):

    logger.info('Registrando la venta')
    ontologyFile = open(db.DBCompras)

    grafoVentas = Graph()
    grafoVentas.bind('default', ECSDI)
    grafoVentas.parse(ontologyFile, format='turtle')

    grafoVentas += grafoFactura

    for item in grafoVentas.subjects(RDF.type, ACL.FipaAclMessage):
        grafoVentas.remove((item, None, None))

    grafoVentas.serialize(destination=db.DBCompras, format='turtle')
    logger.info("Registro de venta finalizado")



def enviarVenta(content, gm, factura_suj, prioridad, precio_prod):
    global GestorEnviosAgent
    global DirectoryAgent
    global TesoreroAgent
    global mss_cnt

    ciudad = gm.value(subject=content, predicate=ECSDI.Ciudad)
    compra = gm.value(subject=content, predicate=ECSDI.De)
    prioridad = gm.value(subject=content, predicate=ECSDI.Prioridad)

    graph_message = Graph()
    graph_message.bind('foaf', FOAF)
    graph_message.bind('dso', DSO)
    graph_message.bind("default", ECSDI)
    graph_message.remove((content, RDF.type, ECSDI.PeticionCompra))

    reg_obj = ECSDI['EnvioCompra' + str(uuid.uuid4())]
    graph_message.add((reg_obj, RDF.type, ECSDI.EnvioCompra))

    graph_message.add((reg_obj,ECSDI.Ciudad,Literal(ciudad,datatype=XSD.string)))


    sujetoProductos = ECSDI['ProductosAdquiridos' + str(uuid.uuid4())]
    graph_message.add((sujetoProductos, RDF.type, ECSDI.ProductosAdquiridos))

    logger.info("COMPRA: " +compra)


    for producto in gm.objects(subject=compra, predicate=ECSDI.Muestra):
        logger.info("producto: " + str(producto))
        
        product_suj = producto

        peso = gm.value(subject=product_suj, predicate=ECSDI.Peso)
        externo = gm.value(subject=product_suj, predicate=ECSDI.Externo)

        logger.info("IMPRIME PESO Y EXTERNO" + str(peso) + ' '+ str(externo))
        

        graph_message.add((product_suj, ECSDI.Peso, Literal(float(peso), datatype=XSD.float)))
        graph_message.add((product_suj, ECSDI.Externo, Literal(str(externo), datatype=XSD.string)))
        graph_message.add((sujetoProductos, ECSDI.Productos, URIRef(product_suj)))

    graph_message.add((reg_obj, ECSDI.Contiene, URIRef(sujetoProductos)))

    graph_message.add((reg_obj, ECSDI.Prioridad, Literal(prioridad, datatype=XSD.int)))

    try:
        if GestorEnviosAgent is None:
            logger.info("Obtiene el agente")
            GestorEnviosAgent = agents.get_agent(DSO.GestorEnviosAgent, VendedorAgent, DirectoryAgent, mss_cnt)

        print ("GestorEnviosAgent " + str(GestorEnviosAgent.uri))
        print ("GestorEnviosAgent " + str(GestorEnviosAgent.address))

        logger.info("Trata de enviar el mensaje")
        graph = send_message(
            build_message(graph_message, perf=ACL.request,
                            sender=VendedorAgent.uri,
                            receiver=GestorEnviosAgent.uri,
                            content=reg_obj,
                            msgcnt=mss_cnt),
            GestorEnviosAgent.address)



        mss_cnt += 1

        ontologyFile = open(db.DBCompras)
        compras = Graph()
        compras.parse(ontologyFile, format='turtle')

        content = list(graph.triples((None, ECSDI.Precio, None)))[0][0]
        precio = float(graph.value(subject=content, predicate=ECSDI.Precio))
        transportistas = list(graph.triples((content, ECSDI.Nombre, None)))
        fecha = graph.value(subject=content, predicate=ECSDI.Fecha)

        
        precio_trans = float(prioridad)#float(graph.value(subject=factura_suj, predicate=ECSDI.Prioridad))
        compras.add((factura_suj, ECSDI.PrecioEnvio, Literal(precio+precio_trans, datatype=XSD.float)))
        compras.add((factura_suj, ECSDI.Fecha, Literal(fecha, datatype=XSD.date)))

        for trans in transportistas:
            compras.add((factura_suj, ECSDI.Transportistas, trans[2]))

        for item in compras.subjects(RDF.type, ACL.FipaAclMessage):
            compras.remove((item, None, None))

        compras.serialize(destination=db.DBCompras, format='turtle')




        tarjeta = list(gm.triples((None, ECSDI.Tarjeta, None)))[0][2]
        usuario = list(gm.triples((None, ECSDI.Usuario, None)))[0][2]
        graph_tes = Graph()
        graph_tes.bind('foaf', FOAF)
        graph_tes.bind('dso', DSO)
        graph_tes.bind("default", ECSDI)
        item = ECSDI['PagarCompra-' + str(uuid.uuid4())]
        graph_tes.add((item, RDF.type, ECSDI.PagarCompra))
        graph_tes.add((item, ECSDI.Tarjeta, tarjeta))
        graph_tes.add((item, ECSDI.Precio, Literal(precio+precio_trans+precio_prod, datatype=XSD.float)))
        graph_tes.add((item, ECSDI.Usuario, usuario))
        graph_tes.add((item, ECSDI.Contiene, factura_suj))
        for producto in gm.objects(subject=compra, predicate=ECSDI.Muestra):
            logger.info("producto: " + str(producto))
            
            product_suj = producto

            peso = gm.value(subject=product_suj, predicate=ECSDI.Peso)
            externo = gm.value(subject=product_suj, predicate=ECSDI.Externo)

            logger.info("IMPRIME PESO Y EXTERNO" + str(peso) + ' '+ str(externo))
            

            graph_tes.add((product_suj, ECSDI.Peso, Literal(float(peso), datatype=XSD.float)))
            graph_tes.add((product_suj, ECSDI.Externo, Literal(str(externo), datatype=XSD.string)))
            graph_tes.add((factura_suj, ECSDI.Productos, URIRef(product_suj)))
        
        if TesoreroAgent is None:
            logger.info("Obtenemos Tesorero Agent")
            TesoreroAgent = agents.get_agent(DSO.TesoreroAgent, VendedorAgent, DirectoryAgent, mss_cnt)

        logger.info("Trata de enviar peticion cobro a Tesorero Agent")
        graph = send_message(
            build_message(graph_tes, perf=ACL.request,
                            sender=VendedorAgent.uri,
                            receiver=TesoreroAgent.uri,
                            content=item,
                            msgcnt=mss_cnt),
            TesoreroAgent.address)
        
        logger.info("Petición de envio y cobro realizada")
        return graph

    except Exception as e:
        print(e)
        logger.info("No ha sido posible enviar la petición de envio")
        return Graph()

def historial(content, gm):
    logger.info('Peticion de historial de compras')

    usuario = gm.value(subject=content, predicate=ECSDI.Usuario)

    ontologyFile = open(db.DBCompras)
    compras = Graph()
    compras.parse(ontologyFile, format='turtle')

    query = """
            prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            prefix xsd:<http://www.w3.org/2001/XMLSchema#>
            prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
            prefix owl:<http://www.w3.org/2002/07/owl#>
            SELECT DISTINCT ?factura ?ciudad ?direccion ?formada ?trans ?fecha ?precioEnvio ?precioProductos
                            ?prioridad ?tarjeta ?usuario 
                where {
                {?factura rdf:type default:Factura } .
                ?factura default:Ciudad ?ciudad .
                ?factura default:Direccion ?direccion .
                ?factura default:FormadaPor ?formada .
                ?factura default:PrecioEnvio ?precioEnvio .
                ?factura default:PrecioProductos ?precioProductos .
                ?factura default:Prioridad ?prioridad .
                ?factura default:Tarjeta ?tarjeta .
                ?factura default:Usuario ?usuario . 
                ?factura default:Transportistas ?trans .
                ?factura default:Fecha ?fecha .
                
                FILTER (?usuario = '""" + str(usuario) + """')}"""

    historial = compras.query(query)

    # Creamos la respuesta
    grafoFactura = Graph()
    grafoFactura.bind('default', ECSDI)
    sujeto = ECSDI['Historial-' + str(uuid.uuid4())]
    grafoFactura.add((sujeto, RDF.type, ECSDI.Historial))  # NO SE SI HAY Historial EN LA ONTO

    for compra in historial:
        grafoFactura.add((sujeto, ECSDI.Factura, compra['factura']))
        grafoFactura.add((compra['factura'], RDF.type, ECSDI.Factura))
        grafoFactura.add((compra['factura'], ECSDI.Ciudad, compra['ciudad']))
        grafoFactura.add((compra['factura'], ECSDI.Direccion, compra['direccion']))
        grafoFactura.add((compra['factura'], ECSDI.FormadaPor, compra['formada']))
        grafoFactura.add((compra['factura'], ECSDI.PrecioEnvio, compra['precioEnvio']))
        grafoFactura.add((compra['factura'], ECSDI.PrecioProductos, compra['precioProductos']))
        grafoFactura.add((compra['factura'], ECSDI.Prioridad, compra['prioridad']))
        grafoFactura.add((compra['factura'], ECSDI.Tarjeta, compra['tarjeta']))
        grafoFactura.add((compra['factura'], ECSDI.Usuario, compra['usuario']))
        grafoFactura.add((compra['factura'], ECSDI.Transportistas, compra['trans']))
        grafoFactura.add((compra['factura'], ECSDI.Fecha, compra['fecha']))

    logger.info("Retornando el historial")
    return grafoFactura


def vender(content, gm):
    logger.info('Petición de compra recibida')

    # Obtenemos tarjeta de credito
    tarjetaCredito = gm.value(subject=content, predicate=ECSDI.Tarjeta) #AÑADIR TARJETA A LA ONTOLOGIA
    prioridad = gm.value(subject=content, predicate=ECSDI.Prioridad) #AÑADIR prioridad A LA ONTOLOGIA
    

    # Creamos la factura 
    grafoFactura = Graph()
    grafoFactura.bind('default', ECSDI)
    logger.info("Creando la factura")
    sujeto = ECSDI['Factura' + str(uuid.uuid4())]
    grafoFactura.add((sujeto, RDF.type, ECSDI.Factura))#NO SE SI HAY FACTURA EN LA ONTO

    # Obtenemos Usuario
    Usuario = gm.value(subject=content, predicate=ECSDI.Usuario)
    grafoFactura.add((sujeto, ECSDI.Usuario, Literal(Usuario, datatype=XSD.string)))

    # Añadimos la tarjeta de credito al grafoFactura
    grafoFactura.add((sujeto, ECSDI.Tarjeta, Literal(tarjetaCredito, datatype=XSD.int)))
    grafoFactura.add((sujeto, ECSDI.Prioridad, Literal(prioridad, datatype=XSD.int)))

    compra = gm.value(subject=content, predicate=ECSDI.De) #ESTO EXISTE EL ECSDI.De??? XDDD
    
    # Obtenemos la dirección y la ciudad postal
    direccion = gm.value(subject=content, predicate=ECSDI.Direccion)
    ciudad = gm.value(subject=content, predicate=ECSDI.Ciudad)

    grafoFactura.add((sujeto,ECSDI.Direccion,Literal(direccion,datatype=XSD.string)))
    grafoFactura.add((sujeto,ECSDI.Ciudad,Literal(ciudad,datatype=XSD.string)))

    # Obtenemos los productos y calculamos el precio total
    precio = 0
    for producto in gm.objects(subject=compra, predicate=ECSDI.Muestra):
        # Obtenemos precio producto
        p = gm.value(subject=producto, predicate=ECSDI.Precio)


        #sumamos a precio total
        precio += float(p)

        #Añadimos el producto al grafoFactura
        grafoFactura.add((sujeto, ECSDI.FormadaPor, URIRef(producto)))

    # Añadimos el precio productos y precio envío
    grafoFactura.add((sujeto, ECSDI.PrecioProductos, Literal(precio, datatype=XSD.float))) #Revisar si hay preciototal en la onto
    #grafoFactura.add((sujeto, ECSDI.PrecioEnvio, Literal(float(prioridad), datatype=XSD.float)))

    # Llamamos a registrarVenda
    thread = threading.Thread(target=RegistrarVenta, args=(grafoFactura,))
    thread.start()
    
    #IMPLEMENTAR ENVIAR VENTA (FALTAN LOS AGENTES ENVIADORES)
    thread = Thread(target=enviarVenta, args=(content, gm, sujeto, prioridad,precio))
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


@app.route("/iface", methods=['GET', 'POST'])
def browser_iface():
    """
    Simplemente es para probar que funciona
    """

    return None
    

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
                response = Graph()
                content = msgdic['content']
                accion = gm.value(subject=content, predicate=RDF.type)

                if accion == ECSDI.PeticionCompra: #AÑADIR EN LA ONTOLOGIA

                    for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                        gm.remove((item, None, None))
                    response = vender(content, gm) #retornamos la factura

                if accion == ECSDI.PeticionHistorialCompras:

                    for item in gm.subjects(RDF.type, ACL.FipaAclMessage):
                        gm.remove((item, None, None))

                    response = historial(content, gm)


                gr = build_message(response,
                               ACL['inform'],
                               sender=VendedorAgent.uri,
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