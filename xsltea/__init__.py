import copy
import logging
import os

logger = logging.getLogger(__name__)

try:
    import lxml.etree as etree
except ImportError as err:
    logger.error("xsltea fails to load: lxml is not available")
    raise

import teapot.templating

from .namespaces import xml
from .exec import ExecNamespace
from .utils import *
from .errors import TemplateEvaluationError

xml_parser = etree.XMLParser(ns_clean=True,
                             remove_blank_text=True,
                             remove_comments=True)

class Template:
    @classmethod
    def from_buffer(cls, buf, filename):
        return cls(etree.fromstring(buf, parser=xml_parser).getroottree(),
                   filename)

    from_string = from_buffer

    def __init__(self, tree, filename, **kwargs):
        super().__init__(**kwargs)
        self.filename = filename
        self.tree = tree
        self._processors = []

    def add_namespace_processor(self, processor_cls, *args, **kwargs):
        processor = processor_cls(self, *args, **kwargs)
        self._processors.append(processor)

    def get_element_id(self, element):
        id = element.get(xml.id)
        if id is not None:
            return id

        id = generate_element_id(self.tree, element)
        element.set(xml.id, id)

        return id

    def process(self, arguments):
        tree = copy.deepcopy(self.tree)
        for processor in self._processors:
            processor.process(tree, arguments)
        clear_element_ids(tree)
        return tree

class Engine(teapot.templating.FileBasedEngine):
    _xmlns = "https://xmlns.zombofant.net/xsltea/eval"

    def __init__(self, *search_path, **kwargs):
        super().__init__(**kwargs)
        self._cache = {}
        self.search_path = list(search_path)

    def _load_template(self, buf, name):
        template = etree.fromstring(buf)
        return template

    def get_template(self, name):
        try:
            return self.cache[name]
        except KeyError:
            pass

        with self.open_template_file(name) as f:
            template = self._load_template(f.read())

        self.cache[name] = template
        return template

    def _result_processor(self, template_name, result):
        globals_dict = dict(result)
        locals_dict = {}
        template = self.get_template(template_name)
        for attr in list(template.xpath("//@eval:*",
                                        namespaces={"eval": self.xmlns})):
            parent = attr.getparent()
            name = attr.attrname
            result = eval(attr, globals_dict, locals_dict)
            if result is None:
                del parent.attrib[name]
            else:
                parent.attrib[name] = str(result)



    def use_template(self, name):
        return self.create_decorator(
            functools.partial(self._result_processor, name))
