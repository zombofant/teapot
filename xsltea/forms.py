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
import xsltea.template

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
            (str(self.xmlns), "for-field"): [self.handle_for_field],
            (str(self.xmlns), "action"): [self.handle_action],
        }
        self.elemhooks = {
            (str(self.xmlns), "for-each-error"): [self.handle_for_each_error],
            (str(self.xmlns), "if-has-error"): [self.handle_if_has_error]
        }

        self._input_handlers = {
            "checkbox": self._input_box_handler,
            "radio": self._input_radiobox_handler,
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

    def _get_id_ast(self, form_ast, descriptor_ast, sourceline):
        return ast.Call(
            ast.Attribute(
                descriptor_ast,
                "key",
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
            ast.Subscript(
                errors_attr,
                ast.Index(
                    descriptor_ast,
                    lineno=elem.sourceline or 0,
                    col_offset=0),
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

    def handle_for_field(self, template, elem, attrib, value, context):
        try:
            form = elem.get(self.xmlns.form, "default_form")
        except KeyError as err:
            raise ValueError(
                "missing required attribute:"
                " @form:{}".format(err))
        form_ast = compile(form, context.filename, "eval", ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(form_ast)

        descriptor_ast = self._get_descriptor_ast(form_ast, value,
                                                  elem.sourceline)

        id_ast = self._get_id_ast(form_ast, descriptor_ast,
                                  elem.sourceline)

        return [], [], ast.Str("for",
                               lineno=elem.sourceline or 0,
                               col_offset=0), id_ast, []

    def handle_action(self, template, elem, attrib, value, context):
        try:
            form = elem.get(self.xmlns.form, "default_form")
        except KeyError as err:
            raise ValueError(
                "missing required attribute:"
                " @form:{}".format(err))
        form_ast = compile(form, context.filename, "eval", ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(form_ast)

        name_ast = ast.Str("name",
                           lineno=elem.sourceline or 0,
                           col_offset=0)

        value_ast = ast.BinOp(
            ast.BinOp(
                ast.Str(teapot.forms.ACTION_PREFIX,
                        lineno=elem.sourceline or 0,
                        col_offset=0),
                ast.Add(lineno=elem.sourceline or 0,
                        col_offset=0),
                ast.Call(
                    ast.Attribute(
                        form_ast,
                        "get_html_field_key",
                        ast.Load(),
                        lineno=elem.sourceline or 0,
                        col_offset=0),
                    [],
                    [],
                    None,
                    None,
                    lineno=elem.sourceline or 0,
                    col_offset=0),
                lineno=elem.sourceline or 0,
                col_offset=0),
            ast.Add(lineno=elem.sourceline or 0,
                    col_offset=0),
            ast.Str(value,
                    lineno=elem.sourceline or 0,
                    col_offset=0),
            lineno=elem.sourceline or 0,
            col_offset=0)

        return [], [], name_ast, value_ast, []


    def handle_field(self, template, elem, attrib, value, context):
        try:
            form = elem.get(self.xmlns.form, "default_form")
            id = elem.get(getattr(self.xmlns, "id"))
            mode = elem.get(self.xmlns.mode)
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

        if elem.tag == xhtml_ns.input or mode is not None:
            type_ = mode or elem.get("type", "text")
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
            namecode = self._get_id_ast(form_ast, descriptor_ast,
                                        elem.sourceline or 0)
        if valuecode is None:
            valuecode = field_ast

        settercode = compile("""\
_form = __form
_descriptor = __descriptor
elem.set("name", _name)
tmp_value = None
if _descriptor in _form.errors:
    tmp_value = _form.errors[_descriptor][0].original_value
    elem.set("class", _errorclass + elem.get("class", ""))
if tmp_value is None:
    tmp_value = _value
elem.set("value", str(tmp_value) if tmp_value is not None else "")""",
                             context.filename,
                             "exec",
                             ast.PyCF_ONLY_AST)

        settercode = xsltea.template.replace_ast_names(settercode, {
            "_name": namecode,
            "_value": valuecode,
            "__form": form_ast,
            "__descriptor": descriptor_ast,
            "_errorclass": ("" if self._errorclass is None
                            else (self._errorclass + " "))}).body

        if valuecode is False:
            del settercode[-2:-1]

        validation_code = compile("""\
if not isinstance(_form, template_storage[{!r}]):
    raise ValueError("Not a valid form object: {{}}".format(
        form))""".format(template.store(teapot.forms.Form)),
                                  context.filename,
                                  "exec",
                                  ast.PyCF_ONLY_AST)

        validation_code = xsltea.template.replace_ast_names(validation_code, {
            "_form": form_ast}).body

        elemcode[:0] = validation_code
        elemcode.extend(settercode)

        if id is not None:
            if id:
                idcode = compile("""\
elem.set("id", _id)""",
                             context.filename,
                             "exec",
                             ast.PyCF_ONLY_AST)
                elemcode.extend(xsltea.template.replace_ast_names(idcode, {
                    "_id": ast.Str(id,
                                   lineno=elem.sourceline or 0,
                                   col_offset=0)}).body)
        else:
            idcode = compile("""\
elem.set("id", elem.get("name"))""",
                             context.filename,
                             "exec",
                             ast.PyCF_ONLY_AST).body
            elemcode.extend(idcode)

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

    def _input_radiobox_handler(self, elem, form_ast, field_ast, context):
        cmpvalue = elem.get("value")
        if not cmpvalue:
            return None, False, []

        cmpcode = compile(cmpvalue, context.filename, "eval",
                          ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(cmpcode)

        valuecode = compile("""
if a == b:
    elem.set("checked", "checked")""",
                            context.filename,
                            "exec",
                            ast.PyCF_ONLY_AST)

        valuecode = xsltea.template.replace_ast_names(valuecode, {
            "a": field_ast,
            "b": cmpcode
            }).body

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
                code.func.value = obj_ast
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
                ast.Add(
                    lineno=elem.sourceline or 0,
                    col_offset=0),
                ast.BinOp(
                    secondscode,
                    ast.Add(
                        lineno=elem.sourceline or 0,
                        col_offset=0),
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
