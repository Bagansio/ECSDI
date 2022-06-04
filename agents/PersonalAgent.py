# -*- coding: utf-8 -*-
"""
filename: PersonalAgent

Antes de ejecutar hay que añadir la raiz del proyecto a la variable PYTHONPATH

Agente que se registra como agente personal, envia y espera peticiones

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

from flask import Flask, request, render_template, session, redirect, Response
from rdflib import Graph, Namespace, Literal, URIRef, XSD
from rdflib.namespace import FOAF, RDF
from utils import db, agents

from AgentUtil.OntoNamespaces import ECSDI
from AgentUtil.ACL import ACL
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.ACLMessages import build_message, send_message, get_message_properties
from AgentUtil.Agent import Agent
from AgentUtil.Logging import config_logger
from AgentUtil.DSO import DSO
from AgentUtil.Ciudades import ciudades
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
    port = agents.agent_ports['PersonalAgent']
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
app.secret_key = 'secret'
app.debug = True
if not args.verbose:
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

# Configuration constants and variables
agn = Namespace("http://www.agentes.org#")

# Contador de mensajes
mss_cnt = 0

# Datos del Agente
PersonalAgent = Agent('PersonalAgent',
                      agn.PersonalAgent,
                      'http://%s:%d/comm' % (hostaddr, port),
                      'http://%s:%d/Stop' % (hostaddr, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

GestorDevolucionesAgent = None

MostradorAgent = None

VendedorAgent = None

# Global dsgraph triplestore
dsgraph = Graph()

# Cola de comunicacion entre procesos
cola1 = Queue()


# Agent Utils


def obtener_productos(form = None):
    global mss_cnt
    global MostradorAgent
    global DirectoryAgent

    form = request.form

    if MostradorAgent is None:
        logger.info('Buscando al agente Mostrador')
        MostradorAgent = agents.get_agent(DSO.MostradorAgent, PersonalAgent, DirectoryAgent, mss_cnt)

        mss_cnt += 1

    gmess = Graph()
    # Construimos el mensaje de registro
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    gmess.bind("default", ECSDI)
    reg_obj = agn['BuscarProductos' + str(mss_cnt)]
    gmess.add((reg_obj, RDF.type, ECSDI.BuscarProductos))

    us = None
    if 'usuario' in session:
        us = session['usuario']

    gmess.add((reg_obj, ECSDI.Id, Literal(us, datatype=XSD.string)))

    if form is not None and 'search' in form:
        buscar_productos(gmess, form, reg_obj)

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos

    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=PersonalAgent.uri,
                      receiver=MostradorAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        MostradorAgent.address)
    mss_cnt += 1

    query = """
                prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                prefix xsd:<http://www.w3.org/2001/XMLSchema#>
                prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
                prefix owl:<http://www.w3.org/2002/07/owl#>
                SELECT ?producto ?nombre ?precio ?marca ?peso ?categoria ?descripcion ?externo
                    where {
                    {?producto rdf:type default:Producto } .
                    ?producto default:Nombre ?nombre .
                    ?producto default:Precio ?precio .
                    ?producto default:Marca ?marca .
                    ?producto default:Peso ?peso .
                    ?producto default:Categoria ?categoria .
                    ?producto default:Descripcion ?descripcion .
                    ?producto default:Externo ?externo .
                    }"""

    graph_query =  gr.query(query)

    return gr.query(query)

def obtener_historial(usuario):


    global PersonalAgent
    global VendedorAgent
    global DirectoryAgent
    global mss_cnt


    if VendedorAgent is None:
        VendedorAgent = agents.get_agent(DSO.VendedorAgent, PersonalAgent, DirectoryAgent, mss_cnt)

    gmess = Graph()
    # Construimos el mensaje de registro
    gmess.bind('foaf', FOAF)
    gmess.bind('dso', DSO)
    gmess.bind("default", ECSDI)
    id = str(uuid.uuid4())
    reg_obj = agn['PeticionHistorial-' + str(id)]
    gmess.add((reg_obj, RDF.type, ECSDI.PeticionHistorialCompras))
    gmess.add((reg_obj, ECSDI.Usuario, URIRef(usuario)))
    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos

    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=PersonalAgent.uri,
                      receiver=VendedorAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        VendedorAgent.address)

    mss_cnt += 1
    query = """
            prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            prefix xsd:<http://www.w3.org/2001/XMLSchema#>
            prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
            prefix owl:<http://www.w3.org/2002/07/owl#>
            SELECT DISTINCT ?factura ?ciudad ?direccion (GROUP_CONCAT(?formada;SEPARATOR=",") AS ?productos) ?precioEnvio ?precioProductos ?prioridad ?tarjeta ?usuario 
                where {
                {?factura rdf:type default:Factura } .
                ?factura default:Ciudad ?ciudad .
                ?factura default:Direccion ?direccion .
                ?factura default:FormadaPor ?formada .
                ?factura default:PrecioEnvio ?precioEnvio .
                ?factura default:PrecioProductos ?precioProductos .
                ?factura default:Prioridad ?prioridad .
                ?factura default:Tarjeta ?tarjeta .
                ?factura default:Usuario ?usuario . }
            GROUP BY ?factura"""

    return gr.query(query)


def buscar_productos(graph, form, suj):
    if form['nombre'] != '':
        graph.add((suj, ECSDI.RestringidaPor, ECSDI.RestriccionNombre))
        graph.add((ECSDI.RestriccionNombre, ECSDI.Nombre, Literal(form['nombre'], datatype=XSD.string)))

    if form['categoria'] != '':
        graph.add((suj, ECSDI.RestringidaPor, ECSDI.RestriccionCategoria))
        graph.add((ECSDI.RestriccionCategoria, ECSDI.Categoria, Literal(form['categoria'], datatype=XSD.string)))

    if form['marca'] != '':
        graph.add((suj, ECSDI.RestringidaPor, ECSDI.RestriccionMarca))
        graph.add((ECSDI.RestriccionMarca, ECSDI.Marca, Literal(form['marca'], datatype=XSD.string)))

    if form['precioMinimo'] != '' or form['precioMaximo'] != '':
        graph.add((suj, ECSDI.RestringidaPor, ECSDI.RestriccionPrecio))

        if form['precioMinimo'] != '':
            graph.add(
                (ECSDI.RestriccionPrecio, ECSDI.PrecioMinimo, Literal(float(form['precioMinimo']), datatype=XSD.float)))

        if form['precioMaximo'] != '':
            graph.add(
                (ECSDI.RestriccionPrecio, ECSDI.PrecioMaximo, Literal(float(form['precioMaximo']), datatype=XSD.float)))


def query_usuario(form, login):
    query = """
                        prefix rdf:<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                        prefix xsd:<http://www.w3.org/2001/XMLSchema#>
                        prefix default:<http://www.owl-ontologies.com/ECSDIPractica#>
                        prefix owl:<http://www.w3.org/2002/07/owl#>
                        SELECT ?usuario ?nombre ?password 
                            where {
                            {?usuario rdf:type default:Usuario } .
                            ?usuario default:Nombre ?nombre .
                            ?usuario default:Password ?password .

                            FILTER(?nombre ='""" + form['username'] + """'"""

    if login:
        query += """ && ?password = '""" + form['password'] + """'"""

    query += """)}"""

    return query


def login(form):
    error = ""
    logger.info(f"Logeando usuario: {form['username']}")
    ontologyFile = open(db.DBUsuarios)
    graph = Graph()
    graph.parse(ontologyFile, format='turtle')
    graph.bind("default", ECSDI)
    graph_query = graph.query(query_usuario(form, True))

    if len(graph_query) > 0:
        for element in graph_query:
            session['usuario'] = element['usuario']

        logger.info("Usuario logeado")

    else:
        error = "Usuario no existente o contraseña erronea"
        logger.info(error)

    return error


def registrar_usuario(form):
    error = ""
    logger.info(f"Registrando usuario: {form['username']}")
    ontologyFile = open(db.DBUsuarios)
    graph = Graph()
    graph.parse(ontologyFile, format='turtle')
    graph.bind("default", ECSDI)
    graph_query = graph.query(query_usuario(form, False))

    if len(graph_query) > 0:
        error = "Usuario ya existente"
        logger.info("Registro del usuario fallido (Ya existe el usuario)")
    else:
        id = str(uuid.uuid4())
        item = ECSDI['Usuario' + id]
        graph.add((item, RDF.type, ECSDI.Usuario))
        graph.add((item, ECSDI.Nombre, Literal(form['username'], datatype=XSD.string)))
        graph.add((item, ECSDI.Password, Literal(form['password'], datatype=XSD.string)))
        graph.serialize(destination=db.DBUsuarios, format='turtle')
        session['usuario'] = item
        logger.info("Registro de nuevo usuario finalizado")
    return error


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
    reg_obj = agn[PersonalAgent.name + '-Register']
    gmess.add((reg_obj, RDF.type, DSO.Register))
    gmess.add((reg_obj, DSO.Uri, PersonalAgent.uri))
    gmess.add((reg_obj, FOAF.name, Literal(PersonalAgent.name)))
    gmess.add((reg_obj, DSO.Address, Literal(PersonalAgent.address)))
    gmess.add((reg_obj, DSO.AgentType, DSO.PersonalAgent))

    # Lo metemos en un envoltorio FIPA-ACL y lo enviamos
    gr = send_message(
        build_message(gmess, perf=ACL.request,
                      sender=PersonalAgent.uri,
                      receiver=DirectoryAgent.uri,
                      content=reg_obj,
                      msgcnt=mss_cnt),
        DirectoryAgent.address)
    mss_cnt += 1

    return gr


@app.route("/iface", methods=['GET', 'POST'])
def browser_iface():
    """
    Permite la comunicacion con el agente via un navegador
    via un formulario
    """

    graph_query = obtener_productos(request.form)
    return render_template('main.html', query=graph_query)

@app.route("/comprar", methods=['GET', 'POST'])
def comprar_iface():

    graph_query = obtener_productos()

    global VendedorAgent
    global DirectoryAgent
    global mss_cnt

    if not 'cart' in session or len(session['cart']) == 0:
        return redirect('iface')

    if not 'usuario' in session:
        return redirect('login')


    productos = []
    for producto in graph_query:
        if str(producto['producto']) in session['cart']:
            productos.append(producto)

    form = request.form
    us = session['usuario']


    if 'comprar' in form:
        if form['numTarjeta'] != '' and form['prioridad'] != '' and form['direccion'] != '' and form['ciudad'] != '':
            if VendedorAgent is None:
                logger.info('Buscando al agente Vendedor')
                VendedorAgent = agents.get_agent(DSO.VendedorAgent, PersonalAgent, DirectoryAgent, mss_cnt)

                mss_cnt += 1

            gmess = Graph()
            # Construimos el mensaje de registro
            gmess.bind('foaf', FOAF)
            gmess.bind('dso', DSO)
            gmess.bind("default", ECSDI)
            id = str(uuid.uuid4())
            reg_obj = agn['PeticionCompra' + str(id)]
            gmess.add((reg_obj, RDF.type, ECSDI.PeticionCompra))
            gmess.add((reg_obj, ECSDI.Usuario, URIRef(us)))
            gmess.add((reg_obj, ECSDI.Prioridad, Literal(int(form['prioridad']), datatype=XSD.int)))
            gmess.add((reg_obj, ECSDI.Tarjeta, Literal(int(form['numTarjeta']), datatype=XSD.int)))
            gmess.add((reg_obj, ECSDI.Direccion, Literal(form['direccion'], datatype=XSD.string)))
            gmess.add((reg_obj, ECSDI.Ciudad, Literal(form['ciudad'], datatype=XSD.string)))

            sujetoCompra = ECSDI['Compra' + str(id)]
            gmess.add((sujetoCompra, RDF.type, ECSDI.Compra))

            for product in productos:
                product_nombre = product['nombre']
                product_precio = product['precio']
                product_peso = product['peso']
                product_externo = product['externo']
                product_suj = product['producto']

                gmess.add((product_suj, RDF.type, ECSDI.Producto))
                gmess.add((product_suj, ECSDI.Nombre, Literal(product_nombre, datatype=XSD.string)))
                gmess.add((product_suj, ECSDI.Precio, Literal(product_precio, datatype=XSD.float)))
                gmess.add((product_suj, ECSDI.Peso, Literal(product_peso, datatype=XSD.float)))
                gmess.add((product_suj, ECSDI.Externo, Literal(product_externo, datatype=XSD.string)))
                gmess.add((sujetoCompra, ECSDI.Muestra, URIRef(product_suj)))

            gmess.add((reg_obj, ECSDI.De, URIRef(sujetoCompra)))


            gr = send_message(
                build_message(gmess, perf=ACL.request, 
                              sender=PersonalAgent.uri,
                              receiver=VendedorAgent.uri,
                              content=reg_obj,
                              msgcnt=mss_cnt),
                VendedorAgent.address)
            mss_cnt += 1

            total = None

            for s, o in gr.subject_objects(ECSDI.PrecioTotal):
                total = o

            session['cart'] = []
            return render_template('factura.html', query=productos, total=total, data=form)



    return render_template('comprar.html', query=productos, cities=ciudades.keys())


@app.route("/historialinfo", methods=['GET','POST'])
def historial_info_iface():

    global GestorDevolucionesAgent
    global DirectoryAgent
    global PersonalAgent
    global mss_cnt

    if not 'usuario' in session:
        return redirect('login')

    formFactura = ECSDI[request.args.get('factura')]
    error = ""

    form = request.form
    historial = obtener_historial(session['usuario'])
    productos = obtener_productos()
    print(formFactura)
    factura = None
    prodinfo = []
    for compra in historial:
        if compra['factura'] == formFactura:
            factura = compra

    if factura is not None:
        prods = factura['productos'].split(',')
        for producto in productos:
            for prod in prods:
                if prod == str(producto['producto']):
                    prodinfo.append(producto)

    if 'devolver' in form:
        gm = Graph()
        gm.bind('foaf', FOAF)
        gm.bind('dso', DSO)
        gm.bind("default", ECSDI)
        reg_obj = agn['PeticionDevolucion-' + str(mss_cnt)]
        gm.add((reg_obj, RDF.type, ECSDI.PeticionDevolucion))
        gm.add((reg_obj, ECSDI.Usuario,  URIRef(session['usuario'])))
        gm.add((reg_obj, ECSDI.Motivo, Literal(form['motivo'], datatype=XSD.string)))
        print(form)
        for p in prodinfo:
            if str(p['producto']) == form['id']:
                gm.add((reg_obj, ECSDI.Producto, URIRef(p['producto'])))
                gm.add((p['producto'], ECSDI.Precio, p['precio']))
                gm.add((p['producto'], ECSDI.Externo, p['externo']))
                gm.add((p['producto'], ECSDI.Peso, p['peso']))

        gm.add((reg_obj, ECSDI.Factura, factura['factura']))
        gm.add((factura['factura'], RDF.type, ECSDI.Factura))
        gm.add((factura['factura'], ECSDI.Tarjeta, factura['tarjeta']))
        gm.add((factura['factura'], ECSDI.Ciudad, factura['ciudad']))
        gm.add((factura['factura'], ECSDI.Fecha, Literal(agents.get_date(2), datatype=XSD.date)))

        if GestorDevolucionesAgent is None:
            GestorDevolucionesAgent = agents.get_agent(DSO.GestorDevolucionesAgent, PersonalAgent, DirectoryAgent, mss_cnt)

        gr = send_message(
            build_message(gm, perf=ACL.request,
                          sender=PersonalAgent.uri,
                          receiver=GestorDevolucionesAgent.uri,
                          content=reg_obj,
                          msgcnt=mss_cnt),
            GestorDevolucionesAgent.address)
        mss_cnt += 1

        estado = list(gr.triples((None, ECSDI.Estado, None)))
        if len(estado) > 0 and str(estado[0][2]) == 'Rechazada':
            error = "El plazo ha expirado"


        agents.print_graph(gr)


    return render_template('historialinfo.html', factura=factura, prods=prodinfo, error=error)

@app.route("/historial", methods=['GET', 'POST'])
def historial_iface():



    if not 'usuario' in session:
        return redirect('login')


    historial = obtener_historial(session['usuario'])

    for h in historial:
        print(h['productos'])
    return render_template('historial.html', query=historial)




@app.route("/login", methods=['GET', 'POST'])
def login_iface():
    if 'usuario' in session:
        return redirect('/iface')
    form = request.form
    error = ""
    if 'login' in form:
        if form['username'] != '' and form['password'] != '':
            error = login(form)

            if error == "":
                return redirect("/iface")
    return render_template('login.html', error=error)


@app.route("/register", methods=['GET', 'POST'])
def register_iface():
    form = request.form
    error = ""
    if 'register' in form:
        if form['username'] != '' and form['password'] != '':
            error = registrar_usuario(form)

            if error == "":
                return redirect("/iface")
    return render_template('register.html', error=error)


@app.route("/logout", methods=['GET', 'POST'])
def logout_iface():
    session.pop('usuario', None)
    logger.info('Usuario deslogeado')
    return redirect('/iface')


@app.route("/addcart", methods=['POST'])
def addcart_iface():
    if 'product' in request.json:
        if 'cart' not in session:
            session['cart'] = []

        temp = session['cart']
        if request.json['product'] not in temp:
            temp.append(request.json['product'])
            session['cart'] = temp

    return Response("ok", status=200)

@app.route("/removecart", methods=['POST'])
def removecart_iface():
    if 'product' in request.json:
        if 'cart' in session:
            temp = session['cart']
            temp.remove(request.json['product'])
            session['cart'] = temp

    return Response("ok", status=200)


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
            Graph(), ACL['not-understood'], sender=PersonalAgent.uri, msgcnt=mss_cnt)
    else:
        # Obtenemos la performativa
        perf = msgdic['performative']

        if perf != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            gr = build_message(
                Graph(), ACL['not-understood'], sender=PersonalAgent.uri, msgcnt=mss_cnt)
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
                               sender=PersonalAgent.uri,
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
