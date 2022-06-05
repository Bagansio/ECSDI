## ECSDI PRACTICA

HECHO POR:

- Alex Moa
- Artur Farriols
- Cristian Mesa


## Introducción 

- Las instrucciones de como iniciar el sistema se encuentran más adelante
- Los agentes se encuentran en el directorio: <b>[agents](/../../agents)</b>
- Las bases de datos se encuentran en el directorio: <b>[data](/../../data)</b>

## Instrucciones para iniciar el sistema:

    1. Ejecutar SimpleDirectoryAgent:
        - python SimpleDirectoryAgent.py 
    2. Ejecutar CentroLogisticoAgent 3 veces con los argumentos --port y --centro:
        - python CentroLogisticoAgent.py --port 9050 --centro 1
        - python CentroLogisticoAgent.py --port 9051 --centro 2
        - python CentroLogisticoAgent.py --port 9052 --centro 3
    3. Ejecutar 3 veces cada transportista con los argumentos --port, --dport (puerto del centro logistico), --centro:
        - python Transportista1Agent.py --port 9030 --dport 9050 --centro 1 
        - python Transportista1Agent.py --port 9031 --dport 9051 --centro 2 
        - python Transportista1Agent.py --port 9032 --dport 9052 --centro 3 
    4. Ejecutar el resto de agentes

    EN CASO QUE SE DESEE EJECUTAR EN MÁS DE UN PC:
        · Añadir el argumento --open sin ningun parametro
        · Añadir el argumento --dhost con el hostname del SimpleDirectoryAgent (lo muestra por terrminial)
                                      o en el caso que sean los transportistas con el hostname del CentroLogisticoAgent

## Juegos de pruebas:

#### 1) Busqueda de productos:

    1. Buscar sin filtro -> Retrona todos los productos de la base de datos.
    2. Buscar por nombre = Agua -> Retorna un producto llamado Agua.
    3. Buscar por precio máximo = 100 -> Retorna los productos con un precio inferior a 100.
    4. Buscar por precio mínimo = 100 -> Retorn a los productos con un precio superior a 100.
    5. Bucar por precio máximo = 25 y mínimo = 20 y Marca = Pull -> Retorna los productos entre ese rango de precio y 
       contengan la marca Pull.

