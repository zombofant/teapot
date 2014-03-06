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

    def __init__(self,
                 errorclass=None,
                 safety_level=xsltea.safe.SafetyLevel.conservative,
                 **kwargs):
        super().__init__(**kwargs)
        self._safety_level = safety_level
        self._errorclass = errorclass

        self.attrhooks = {
            (str(self.xmlns), "field"): [self.handle_field],
            (str(self.xmlns), "form"): [self.handle_form],
        }
        self.elemhooks = {
            (str(self.xmlns), "for-each-error"): [self.handle_for_each_error],
            (str(self.xmlns), "if-has-error"): [self.handle_if_has_error]
        }

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

    def _get_descriptor_ast(self, form_ast, fieldname, sourceline):
        return ast.Attribute(
            ast.Call(
                ast.Name("type",
                         ast.Load(),
                         lineno=sourceline or 0,
                         col_offset=0),
                [
                    form_ast
                ],
                [],
                None,
                None,
                lineno=sourceline or 0,
                col_offset=0),
            fieldname,
            ast.Load(),
            lineno=sourceline or 0,
            col_offset=0)

    def handle_if_has_error(self, template, elem, context, offset):
        try:
            form = elem.get(self.xmlns.form, "default_form")
            field = elem.attrib[self.xmlns.field]
        except KeyError as err:
            raise ValueError("Missing required attribute @form:{} on "
                             "form:for-each-error".format(err)) from None

        form_ast = compile(form, context.filename, "eval", ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(form_ast)

        condition_ast = ast.Compare(
            self._get_descriptor_ast(
                form_ast, field,
                elem.sourceline),
            [ast.In()],
            [ast.Attribute(
                form_ast,
                "errors",
                ast.Load(),
                lineno=elem.sourceline or 0,
                col_offset=0)],
            lineno=elem.sourceline or 0,
            col_offset=0)

        return xsltea.exec.ExecProcessor.create_if(
            template, elem, context, offset,
            condition_ast)

    def handle_for_each_error(self, template, elem, context, offset):
        try:
            form = elem.get(self.xmlns.form, "default_form")
            field = elem.attrib[self.xmlns.field]
        except KeyError as err:
            raise ValueError("Missing required attribute @form:{} on "
                             "form:for-each-error".format(err)) from None

        form_ast = compile(form, context.filename, "eval", ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(form_ast)

        errors_attr = ast.Attribute(
            form_ast,
            "errors",
            ast.Load(),
            lineno=elem.sourceline or 0,
            col_offset=0)

        descriptor_ast = self._get_descriptor_ast(
            form_ast, field,
            elem.sourceline)

        iter_ast = ast.IfExp(
            ast.Compare(
                descriptor_ast,
                [ast.In(lineno=elem.sourceline or 0,
                        col_offset=0)],
                [errors_attr],
                lineno=elem.sourceline or 0,
                col_offset=0),
            ast.List(
                [
                    ast.Subscript(
                        errors_attr,
                        ast.Index(
                            descriptor_ast,
                            lineno=elem.sourceline or 0,
                            col_offset=0),
                        ast.Load(),
                        lineno=elem.sourceline or 0,
                        col_offset=0)
                ],
                ast.Load(),
                lineno=elem.sourceline or 0,
                col_offset=0),
            ast.List(
                [],
                ast.Load(),
                lineno=elem.sourceline or 0,
                col_offset=0),
            lineno=elem.sourceline or 0,
            col_offset=0)

        bind_ast = ast.Name(
            "error",
            ast.Store(),
            lineno=elem.sourceline or 0,
            col_offset=0)

        return xsltea.safe.ForeachProcessor.create_foreach(
            template, elem, context, offset,
            bind_ast, iter_ast)


    def handle_form(self, template, elem, attrib, value, context):
        form_ast = compile(value,
                           context.filename,
                           "eval",
                           ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(form_ast)

        elemcode = compile("""\
default_form = a""",
                           context.filename,
                           "exec",
                           ast.PyCF_ONLY_AST).body
        elemcode[0].value = form_ast

        return [], elemcode, None, None, []

    def handle_field(self, template, elem, attrib, value, context):
        try:
            form = elem.get(self.xmlns.form, "default_form")
        except KeyError as err:
            raise ValueError(
                "missing required attribute:"
                " @form:{}".format(err))

        form_ast = compile(form, context.filename, "eval", ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(form_ast)

        field_ast = ast.Attribute(
            form_ast,
            value,
            ast.Load(),
            lineno=elem.sourceline or 0,
            col_offset=0)

        descriptor_ast = self._get_descriptor_ast(
            form_ast, value,
            elem.sourceline)

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
            elem, form_ast, field_ast, context)
        if namecode is None:
            namecode = ast.Call(
                ast.Attribute(
                    descriptor_ast,
                    "key",
                    ast.Load(),
                    lineno=elem.sourceline or 0,
                    col_offset=0),
                [
                    form_ast
                ],
                [],
                None,
                None,
                lineno=elem.sourceline or 0,
                col_offset=0)
        if valuecode is None:
            valuecode = field_ast

        settercode = compile("""\
elem.set("name", a)
tmp_value = b
elem.set("value", str(tmp_value) if tmp_value is not None else "")
if b in a.errors:
    elem.set("class", {!r} + elem.get("class", ""))""".format(
        self._errorclass),
                             context.filename,
                             "exec",
                             ast.PyCF_ONLY_AST).body

        if self._errorclass:
            settercode[3].test.left = descriptor_ast
            settercode[3].test.comparators[0].value = form_ast
        else:
            del settercode[3]
        if valuecode:
            settercode[1].value = valuecode
        else:
            del settercode[1:3]
        if namecode:
            settercode[0].value.args[1] = namecode
        else:
            del settercode[0]

        validation_code = compile("""\
if not isinstance(form, template_storage[{!r}]):
    raise ValueError("Not a valid form object: {{}}".format(
        form))""".format(template.store(teapot.forms.Form)),
                                  context.filename,
                                  "exec",
                                  ast.PyCF_ONLY_AST).body

        validation_code[0].test.operand.args[0] = form_ast

        elemcode[:0] = validation_code
        elemcode.extend(settercode)

        return [], elemcode, None, None, []

    def _input_box_handler(self, elem, form_ast, field_ast, context):
        valuecode = compile("""
if a:
    elem.set("checked", "checked")""",
                            context.filename,
                            "exec",
                            ast.PyCF_ONLY_AST).body

        valuecode[0].test = field_ast

        return None, False, valuecode

    def _input_text_handler(self, elem, form_ast, field_ast, context):
        return None, None, []

    def _input_datetime_handler(self, fmt, elem, form_ast, field_ast, context):
        def partcode(part, obj_ast):
            if "%" in part:
                code = compile("""\
a.strftime({!r})""".format(part),
                               context.filename,
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
                                  context.filename,
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

    def _textarea_handler(self, elem, form_ast, field_ast, context):
        elemcode = compile("""\
elem.text = str(a)""",
                           context.filename,
                           "exec",
                           ast.PyCF_ONLY_AST).body
        elemcode[0].value.args[0] = field_ast

        return None, False, elemcode

    def _select_handler(self, elem, form_ast, field_ast, context):
        logger.warn("select inputs are not entirely supported yet")
        return None, False, []
