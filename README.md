## ECSDI PRACTICA

HECHO POR:

- Alex Moa
- Artur Farriols
- Cristian Mesa


## Introducción 

- Las instrucciones de como iniciar el sistema se encuentran más adelante
- Los agentes se encuentran en el directorio: <b>[agents](/../../tree/master/agents)</b>
- Las bases de datos se encuentran en el directorio: <b>[data](/../../tree/master/data)</b>

## Instrucciones para iniciar el sistema:

    1. Ejecutar SimpleDirectoryAgent:

        - python SimpleDirectoryAgent.py 

    2. Ejecutar CentroLogisticoAgent 3 veces con los argumentos
       --port y --centro:

        - python CentroLogisticoAgent.py --port 9050 --centro 1
        - python CentroLogisticoAgent.py --port 9051 --centro 2
        - python CentroLogisticoAgent.py --port 9052 --centro 3

    3. Ejecutar 3 veces cada transportista con los argumentos
       --port, --dport (puerto del centro logistico), --centro:

        - python Transportista1Agent.py --port 9030 --dport 9050 --centro 1 
        - python Transportista1Agent.py --port 9031 --dport 9051 --centro 2 
        - python Transportista1Agent.py --port 9032 --dport 9052 --centro 3 
    
    4. Ejecutar el resto de agentes

    EN CASO QUE SE DESEE EJECUTAR EN MÁS DE UN PC:

        · Añadir el argumento --open sin ningun parametro
        · Añadir el argumento --dhost con el hostname del SimpleDirectoryAgent (lo muestra por terrminial)
                                      o en el caso que sean los transportistas con el hostname del 
                                      CentroLogisticoAgent

## Juegos de pruebas:



#### 1) Busqueda de productos:

   1. Buscar sin filtro -> Retorna todos los productos de la base de datos.
   2. Buscar por nombre = Agua -> Retorna un producto llamado Agua.
   3. Buscar por precio máximo = 100 -> Retorna los productos con un precio inferior o igual a 100.
   4. Buscar por precio mínimo = 100 -> Retorna los productos con un precio superior o igual a 100.
   5. Bucar por precio máximo = 25 y mínimo = 20 y Marca = Pull -> Retorna los productos entre ese 
       rango de precio y contengan la marca Pull.
       
#### 2) Compra:
   
   Para añadir productos al carrito hay que pulsar al boton:
   <img src="agents/static/icons/purchase.png" widht=35 height=35></img>
   
   1. Añadir el producto Agua de Marca FuenteBonita, ir a la pestaña "Compra" y agregar el atributo 
       Tarjeta = 2222 , Prioridad = Cuando Llegue, Direccion = Avenida Primera y Ciudad = Barcelona
       
       Factura correcta con información parcial. Transcurrido unos segundos, ir a la pestaña "Compras"
       donde se mostrara el historial de compras del usuario, buscar la compra con los datos previos y darle al boton: 
       <img src="agents/static/icons/info.png" widht=35 height=35></img>
      
       Allí observar que el precio total han sido 2.5€ junto al resto de datos
       Observar en el TesoreroAgent el cobro y que se ha pagado a "Cola-Coca"
      
#### 3) Devolver:
    
   1. Ir a la pestaña "Compras", darle al icono:  <img src="agents/static/icons/info.png" widht=35 height=35></img>

       Seleccionar la compra con direccion = Casa y tarjeta = 2222. Una vez cargada la pagina, pulsar el boton Devolver.

       Comprobar que muestra que el producto ya se ha devuelto previamente

   2. Ir a la pestaña "Compras", darle al icono:  <img src="agents/static/icons/info.png" widht=35 height=35></img>

       Seleccionar la compra con direccion = Casa y tarjeta = 3333. Una vez cargada la pagina, pulsar el boton Devolver.

       Comprobar que muestra que el plazo ha expirado

   3. Ir a la pestaña "Compras", darle al icono:  <img src="agents/static/icons/info.png" widht=35 height=35></img>

        Seleccionar la compra con direccion = Casa y tarjeta = 4444. Una vez cargada la pagina, pulsar el boton Devolver.

        Comprobar que muestra que esta aceptada y procesando. Transcurrido unos segundos, ir a la pestaña "Devoluciones",
        observar que hay una nueva devolucion añadida y el tesorero ha devuelto el dinero
      
