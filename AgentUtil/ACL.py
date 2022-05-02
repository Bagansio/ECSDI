"""
.. module:: ACL

 Translated by owl2rdflib

 Translated to RDFlib from ontology http://www.nuin.org/ontology/fipa/acl

 :Date 03/02/2021 07:33:14
"""
from rdflib import URIRef
from rdflib.namespace import ClosedNamespace

ACL =  ClosedNamespace(
    uri=URIRef('http://www.nuin.org/ontology/fipa/acl'),
    terms=[
        # Classes
        'FipaAclMessage',
        'KsMessage',
        'SpeechAct',

        # Object properties
        'receiver',
        'reply-to',
        'ontology',
        'performative',
        'sender',

        # Data properties
        'language',
        'encoding',
        'content',
        'reply-by',
        'reply-with',
        'conversation-id',
        'in-reply-to',

        # Named Individuals
        'refuse',
        'subscribe',
        'agree',
        'query-ref',
        'request',
        'request-whenever',
        'query-if',
        'proxy',
        'cancel',
        'propose',
        'cfp',
        'reject-proposal',
        'failure',
        'accept-proposal',
        'not-understood',
        'inform',
        'inform-if',
        'inform-ref',
        'propagate',
        'confirm',
        'request-when',
        'disconfirm'
    ]
)
