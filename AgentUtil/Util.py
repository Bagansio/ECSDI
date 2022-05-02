"""
.. module:: Util.py

Util.py
******

:Description: Util.py

    Different Auxiliary functions used for different purposes

:Authors:
    bejar

:Version: 

:Date:  23/02/2021
"""
import socket
from pif import get_public_ip

__author__ = 'bejar'

def gethostname():
    try:
        return socket.gethostbyaddr(get_public_ip())[0]
    except:
        return socket.gethostname()