"""
``xsltea.forms`` — Support for ``teapot.forms``
###############################################

"""
import ast
import copy
import functools
import logging

import lxml.etree as etree

import teapot.forms

import xsltea.safe
import xsltea.exec
import xsltea.template

from .processor import TemplateProcessor
from .namespaces import NamespaceMeta, xhtml_ns, shared_ns

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
            (str(shared_ns), "if", str(self.xmlns), "field-error"): [
                self.cond_field_error],
            (str(shared_ns), "case", str(self.xmlns), "field-error"): [
                self.cond_field_error],
            (str(xhtml_ns), "input", str(self.xmlns), "action"): [self.handle_attr_action],
            (str(xhtml_ns), "button", str(self.xmlns), "action"): [self.handle_attr_action],
            (str(xhtml_ns), "input", str(self.xmlns), "form"): [self.attr_noop],
            (str(xhtml_ns), "button", str(self.xmlns), "form"): [self.attr_noop],
            (str(self.xmlns), "form"): [self.handle_attr_form],
            (str(self.xmlns), "field"): [self.warn_attr_usage],
            (str(self.xmlns), "id"): [self.warn_attr_usage],
            (str(self.xmlns), "mode"): [self.warn_attr_usage],
            (str(self.xmlns), "action"): [self.warn_attr_usage],
            (str(self.xmlns), "for"): [self.handle_attr_for],
            (str(self.xmlns), "for-field"): [self.handle_attr_for],
        }
        self.elemhooks = {
            (str(xhtml_ns), "input"): [self.handle_input],
            (str(xhtml_ns), "textarea"): [self.handle_input],
            (str(xhtml_ns), "select"): [self.handle_input],
            (str(self.xmlns), "for-each-error"): [self.handle_for_each_error]
        }

    def _ast_form(self, template, formstr, context, sourceline):
        if formstr is None:
            return ast.Name(
                "default_form",
                ast.Load(),
                lineno=sourceline,
                col_offset=0)

        form_ast = compile(formstr,
                           context.filename,
                           "eval",
                           ast.PyCF_ONLY_AST).body

        self._safety_level.check_safety(form_ast)

        return form_ast

    def _ast_field(self, form_ast, field_name, sourceline):
        return ast.Attribute(
            ast.Call(
                ast.Name(
                    "type",
                    ast.Load(),
                    lineno=sourceline,
                    col_offset=0),
                [
                    form_ast,
                ],
                [],
                None,
                None,
                lineno=sourceline,
                col_offset=0),
            field_name,
            ast.Load(),
            lineno=sourceline,
            col_offset=0)

    def cond_field_error(self, template, elem, key, value, context):
        sourceline = elem.sourceline or 0

        form_ast = self._ast_form(
            template,
            None,
            context,
            sourceline)

        condition_ast = ast.Compare(
            self._ast_field(
                form_ast,
                value,
                sourceline),
            [ast.In()],
            [ast.Attribute(
                form_ast,
                "errors",
                ast.Load(),
                lineno=sourceline,
                col_offset=0)],
            lineno=elem.sourceline or 0,
            col_offset=0)

        return [], [], None, condition_ast, []

    def handle_attr_action(self, template, elem, key, value, context):
        sourceline = elem.sourceline or 0

        form_ast = self._ast_form(
            template,
            elem.get(self.xmlns.form, None),
            context,
            sourceline)

        name_ast = ast.Str(
            "name",
            lineno=sourceline,
            col_offset=0)

        value_ast = ast.BinOp(
            ast.BinOp(
                ast.Str(teapot.forms.ACTION_PREFIX,
                        lineno=sourceline,
                        col_offset=0),
                ast.Add(),
                ast.Call(
                    ast.Attribute(
                        form_ast,
                        "get_html_field_key",
                        ast.Load(),
                        lineno=sourceline,
                        col_offset=0),
                    [],
                    [],
                    None,
                    None,
                    lineno=sourceline,
                    col_offset=0),
                lineno=sourceline,
                col_offset=0),
            ast.Add(),
            ast.Str(value,
                    lineno=sourceline,
                    col_offset=0),
            lineno=sourceline,
            col_offset=0)

        return [], [], name_ast, value_ast, []

    def handle_attr_form(self, template, elem, key, value, context):
        sourceline = elem.sourceline or 0

        form_ast = compile(value,
                           context.filename,
                           "eval",
                           ast.PyCF_ONLY_AST).body

        self._safety_level.check_safety(form_ast)

        elemcode = [
            ast.Assign(
                [
                    ast.Name(
                        "default_form",
                        ast.Store(),
                        lineno=sourceline,
                        col_offset=0),
                ],
                form_ast,
                lineno=sourceline,
                col_offset=0)
        ]

        return [], elemcode, None, None, []

    def handle_attr_for(self, template, elem, key, value, context):
        sourceline = elem.sourceline or 0

        form_ast = self._ast_form(
            template,
            elem.get(self.xmlns.form, None),
            context,
            sourceline)

        field_ast = self._ast_field(
            form_ast,
            value,
            sourceline)

        name_ast = ast.Str(
            "for",
            lineno=sourceline,
            col_offset=0)

        value_ast = ast.Call(
            ast.Attribute(
                field_ast,
                "key",
                ast.Load(),
                lineno=sourceline,
                col_offset=0),
            [
                form_ast,
            ],
            [],
            None,
            None,
            lineno=sourceline,
            col_offset=0)

        return [], [], name_ast, value_ast, []

    def handle_for_each_error(self, template, elem, context, offset):
        sourceline = elem.sourceline or 0
        attrib = elem.attrib

        field = attrib.get("field", None)
        if field is None:
            raise ValueError("Missing required attribute @field on"
                             " form:for-each-error")

        form_ast = self._ast_form(
            template,
            elem.get("form", None),
            context,
            sourceline)

        if field is not None:
            field_ast = self._ast_field(
                form_ast,
                field,
                sourceline)
        else:
            field_ast = ast.Name(
                "None",
                ast.Load(),
                lineno=sourceline,
                col_offset=0)

        errors_ast = ast.Call(
            ast.Attribute(
                ast.Attribute(
                    form_ast,
                    "errors",
                    ast.Load(),
                    lineno=sourceline,
                    col_offset=0),
                "get",
                ast.Load(),
                lineno=sourceline,
                col_offset=0),
            [
                field_ast,
                ast.List(
                    [],
                    ast.Load(),
                    lineno=sourceline,
                    col_offset=0)
            ],
            [],
            None,
            None,
            lineno=sourceline,
            col_offset=0)

        return xsltea.safe.ForeachProcessor.create_foreach(
            template, elem, context, offset,
            ast.Name(
                "error",
                ast.Store(),
                lineno=sourceline,
                col_offset=0),
            errors_ast)



    def _elemcode_input_checkbox(self, form, field, elem):
        if field.__get__(form, type(form)):
            elem.set("checked", "checked")

    def _elemcode_input_radio(self, form, field, elem):
        strvalue = field.to_field_value(form, "radio")
        if elem.get("value") == strvalue:
            elem.set("checked", "checked")

    def _elemcode_input_select(self, context, form, field, elem,
                               put_options,
                               multiple):
        field_value = field.to_field_value(form, "select")
        if multiple:
            elem.set("multiple", "multiple")

        if put_options:
            if hasattr(field, "get_html_options"):
                field.get_html_options(form, context, elem)
            else:
                for key, value in field.get_options(form, context):
                    option = etree.SubElement(
                        elem,
                        xhtml_ns.option)
                    option.set("value", key)
                    option.text = value

                    if key == field_value:
                        option.set("selected", "selected")
        else:
            for option in elem.xpath(".//html:option",
                                     namespaces={"html": str(xhtml_ns)}):
                if option.get("value", option.text) == field_value:
                    option.set("selected", "selected")
                    break


    def _elemcode_input_default(self, form, field, field_type,
                                elem, original_value):
        value = original_value

        if value is None:
            value = field.to_field_value(
                form,
                field_type)

        if value is not None:
            if field_type == "textarea":
                elem.text = value
            else:
                elem.set("value", value)

    def elemcode_input(self,
                       context,
                       append_children,
                       field_type,
                       form, field, childfun,
                       attrib):
        makeelement = context.makeelement

        if not isinstance(form, teapot.forms.Form):
            raise ValueError("Not a valid form object: {}".format(form))

        if field_type is None:
            try:
                field_type = field.field_type
            except AttributeError:
                raise ValueError("Can not infer type of field {}".format(field))

        if not isinstance(field_type, str):
            field_type, *attributes = field_type
        else:
            attributes = ()

        if field_type in {"select", "textarea"}:
            elem = makeelement(getattr(xhtml_ns, field_type), **attrib)
        else:
            elem = makeelement(xhtml_ns.input, **attrib)
            elem.set("type", field_type)

        allow_options = field_type == "select"
        if allow_options and childfun:
            append_children(elem, childfun())

        elem.set("name", field.key(form))

        try:
            original_value = form.errors[field][0].original_value
        except (KeyError, IndexError):
            original_value = None
        else:
            # field has errors
            if self._errorclass is not None:
                elem.set("class", elem.get("class", "") + " " + self._errorclass)

        if field_type == "checkbox":
            self._elemcode_input_checkbox(form, field, elem)
        elif field_type == "radio":
            self._elemcode_input_radio(form, field, elem)
        elif field_type == "select":
            put_options = childfun is None or len(elem) == 0
            self._elemcode_input_select(context, form, field, elem,
                                        put_options,
                                        "multiple" in attributes)
        else:
            self._elemcode_input_default(form, field, field_type,
                                         elem, original_value)

        if elem.get("id") is None:
            elem.set("id", elem.get("name"))

        yield elem

    def handle_input(self, template, elem, context, offset):
        attrib = elem.attrib
        sourceline = elem.sourceline or 0

        try:
            field = attrib[self.xmlns.field]
        except KeyError:
            # not a form input
            return template.default_subtree(elem, context, offset)

        form_ast = self._ast_form(
            template,
            attrib.get(self.xmlns.form),
            context,
            sourceline
        )

        childfun_name = "children{}".format(offset)
        precode = template.compose_childrenfun(
            elem, context, childfun_name)

        elem_localname = xsltea.template.split_tag(elem.tag)[1]
        if elem_localname in {"select", "textarea"}:
            input_type = elem_localname
        else:
            # if input_type is None, the type will be inferred from the field
            input_type = attrib.get("type")

        if input_type is not None:
            input_type = ast.Str(
                input_type,
                lineno=sourceline,
                col_offset=0)
        else:
            input_type = ast.Name(
                "None",
                ast.Load(),
                lineno=sourceline,
                col_offset=0)

        sanitized_attribs = {
            key: value
            for key, value in attrib.items()
            if xsltea.template.split_tag(key)[0] != str(self.xmlns)
        }

        elemcode = [
            ast.Expr(
                ast.YieldFrom(
                    template.ast_store_and_call(
                        self.elemcode_input,
                        [
                            ast.Name(
                                "context",
                                ast.Load(),
                                lineno=sourceline,
                                col_offset=0),
                            template.ast_get_util(
                                "append_children",
                                sourceline),
                            input_type,
                            form_ast,
                            self._ast_field(form_ast, field, sourceline),
                            childfun_name if precode else "None",
                            template.ast_get_stored(
                                template.store(sanitized_attribs),
                                sourceline)
                        ],
                        sourceline=sourceline).value,
                    lineno=sourceline,
                    col_offset=0),
                lineno=sourceline,
                col_offset=0)
        ]

        return precode, elemcode, []


    def warn_attr_usage(self, template, elem, key, value, context):
        sourceline = elem.sourceline or 0
        logger.warn("%s:%d: attribute @form:%s appeared on element %s, which is"
                    " not a supported location of that attribute",
                    context.filename,
                    sourceline,
                    xsltea.template.split_tag(key)[1],
                    elem.tag)
        logger.info("%s:%d: are you missing a form:field attribute?",
                    context.filename,
                    sourceline)

        return [], [], None, None, []

    def attr_noop(self, template, elem, key, value, context):
        return [], [], None, None, []
