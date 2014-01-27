import binascii
import random

from .namespaces import xml

__all__ = [
    "clear_element_ids",
    "generate_element_id",
    "get_element_by_id",
    ]

_element_id_rng = random.Random()
_element_id_rng.seed()

def clear_element_ids(tree):
    for attrib in tree.xpath("//@xml:id",
                             namespaces={"xml": str(xml)}):
        del attrib.getparent().attrib[attrib.attrname]

def generate_element_id(tree, element):
    while True:
        randbytes = _element_id_rng.getrandbits(128).to_bytes(16, 'little')
        elemid = "id"+binascii.b2a_hex(randbytes).decode()
        if not tree.xpath("//*[xml:id='{}']".format(elemid),
                          namespaces={"xml": str(xml)}):
            break
    return elemid

def get_element_by_id(tree, element_id):
    global xml
    return tree.xpath("//*[@xml:id = '"+element_id+"']",
                      namespaces={"xml": str(xml)}).pop()
