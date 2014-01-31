"""
Utilities
#########

Some utilities for working with the lxml ElementTree API.

Uniquely identifying elements
=============================

.. autofunction:: get_element_by_id

"""

import binascii
import random

# FIXME: provide drop-in replacement if blist is not available
from blist import sortedlist

from .namespaces import xml

__all__ = [
    "get_element_by_id",
    ]

def get_element_by_id(tree, element_id):
    """
    Return the element having the given *element_id* in the given *tree* and
    raises :class:`IndexError` if no element has that id.
    """
    global xml
    return tree.xpath("//*[@xml:id = '"+element_id+"']",
                      namespaces={"xml": str(xml)}).pop()
