"""
``xsltea.forms`` — Support for ``teapot.forms``
###############################################

"""
import ast
import copy
import functools
import logging

import teapot.forms

import xsltea.safe

from .processor import TemplateProcessor
from .namespaces import NamespaceMeta, xhtml_ns

logger = logging.getLogger(__name__)

class form_ns(metaclass=NamespaceMeta):
    xmlns = "https://xmlns.zombofant.net/xsltea/form"

class FormProcessor(TemplateProcessor):
    xmlns = form_ns

    def __init__(self, safety_level=xsltea.safe.SafetyLevel.conservative,
                 **kwargs):
        super().__init__(**kwargs)
        self._safety_level = safety_level

        self.attrhooks = {
            (str(self.xmlns), "field"): [self.handle_field],
            (str(self.xmlns), "form"): [self.handle_form]
        }
        self.elemhooks = {}

        self._input_handlers = {
            "checkbox": self._input_box_handler,
            "radio": self._input_box_handler,
            "hidden": self._input_text_handler,
            "text": self._input_text_handler,
            "search": self._input_text_handler,
            "tel": self._input_text_handler,
            "url": self._input_text_handler,
            "email": self._input_text_handler,
            "password": self._input_text_handler,
            "datetime": functools.partial(
                self._input_datetime_handler,
                "%Y-%m-%dT%H:%M:%SZ"),
            "date": functools.partial(
                self._input_datetime_handler,
                "%Y-%m-%d"),
            "month": functools.partial(
                self._input_datetime_handler,
                "%Y-%m"),
            "week": functools.partial(
                self._input_datetime_handler,
                "%Y-W%V"),
            "time": functools.partial(
                self._input_datetime_handler,
                "%H:%M:%S"),
            "number": self._input_text_handler,
        }

    def handle_form(self, template, elem, attrib, value, filename):
        return [], [], None, None, []

    def handle_field(self, template, elem, attrib, value, filename):
        try:
            form = elem.get(self.xmlns.form, "form")
        except KeyError as err:
            raise ValueError(
                "missing required attribute:"
                " @form:{}".format(err))

        form_ast = compile(form, filename, "eval", ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(form_ast)

        field_ast = ast.Attribute(
            form_ast,
            value,
            ast.Load(),
            lineno=elem.sourceline or 0,
            col_offset=0)

        if elem.tag == xhtml_ns.input:
            type_ = elem.get("type", "text")
            try:
                handler = self._input_handlers[type_]
            except KeyError as err:
                raise ValueError("Unsupported html:input@type: {!s}".format(
                    err))
        elif elem.tag == xhtml_ns.textarea:
            handler = self._textarea_handler
        elif elem.tag == xhtml_ns.select:
            handler = self._select_handler
        else:
            raise ValueError("Unsupported form element: {}".format(
                elem.tag))

        namecode, valuecode, elemcode = handler(
            elem, form_ast, field_ast, filename)
        if namecode is None:
            namecode = ast.Str(value,
                               lineno=elem.sourceline or 0,
                               col_offset=0)
        if valuecode is None:
            valuecode = field_ast

        settercode = compile("""\
elem.set("name", a)
elem.set("value", str(b))""",
                             filename,
                             "exec",
                             ast.PyCF_ONLY_AST).body

        if valuecode:
            settercode[1].value.args[1].args[0] = valuecode
        else:
            del settercode[1]
        if namecode:
            settercode[0].value.args[1] = namecode
        else:
            del settercode[0]

        validation_code = compile("""\
if not isinstance(form, template_storage[{!r}]):
    raise ValueError("Not a valid form object: {{}}".format(
        form))""".format(template.store(teapot.forms.Form)),
                                  filename,
                                  "exec",
                                  ast.PyCF_ONLY_AST).body

        validation_code[0].test.operand.args[0] = form_ast

        elemcode[:0] = validation_code
        elemcode.extend(settercode)

        return [], elemcode, None, None, []

    def _input_box_handler(self, elem, form_ast, field_ast, filename):
        valuecode = compile("""
if a:
    elem.set("checked", "checked")""",
                            filename,
                            "exec",
                            ast.PyCF_ONLY_AST).body

        valuecode[0].test = field_ast

        return None, False, valuecode

    def _input_text_handler(self, elem, form_ast, field_ast, filename):
        return None, None, []

    def _input_datetime_handler(self, fmt, elem, form_ast, field_ast, filename):
        def partcode(part, obj_ast):
            if "%" in part:
                code = compile("""\
a.strftime({!r})""".format(part),
                               filename,
                               "eval",
                               ast.PyCF_ONLY_AST).body
                code.func = obj_ast
                return code
            else:
                return ast.Str(part,
                               lineno=elem.sourceline or 0,
                               col_offset=0)

        pre, seconds_part, post = fmt.partition("%S")
        if seconds_part is not None:
            precode = partcode(pre, field_ast)
            postcode = partcode(post, field_ast)

            secondscode = compile("""\
"{:06.3f}".format(a.second + (a.microsecond / 1000000))""",
                                  filename,
                                  "eval",
                                  ast.PyCF_ONLY_AST).body
            secondscode.args[0].left.value = field_ast
            secondscode.args[0].right.left.value = field_ast

            valuecode = ast.BinOp(
                precode,
                "+",
                ast.BinOp(
                    secondscode,
                    "+",
                    postcode,
                    lineno=elem.sourceline or 0,
                    col_offset=0),
                lineno=elem.sourceline or 0,
                col_offset=0)
        else:
            valuecode = partcode(fmt, field_ast)

        return None, valuecode, []

    def _textarea_handler(self, elem, form_ast, field_ast, filename):
        elemcode = compile("""\
elem.text = str(a)""",
                           filename,
                           "exec",
                           ast.PyCF_ONLY_AST).body
        elemcode[0].value.args[0] = field_ast

        return None, False, elemcode

    def _select_handler(self, elem, form_ast, field_ast, filename):
        logger.warn("select inputs are not entirely supported yet")
        return None, False, []