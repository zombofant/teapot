import ast
import copy
import functools

import xsltea.processor
import xsltea.safe

import lxml.etree as etree

from xsltea.namespaces import NamespaceMeta, xhtml_ns, shared_ns

class Context:
    named_columns = None
    pageobj_ast = None
    viewobj_ast = None
    href_key = None

class SortableTableProcessor(xsltea.processor.TemplateProcessor):
    """
    This processor allows for tables which support automatic sorting, provided
    that the data is supplied through an :class:`teapot.sqlalchemy.dbview.View`
    object.

    The usage is as simple as (we assume that the default namespace is XHTML
    here)::

      <tea:sortable-table tea:page="view"
                          tea:routable="routable">
        <colgroup>
          <col name="id" />
          <col name="modified" />
          <col name="station" />
          <col name="submitter" />
          <col name="start_time" />
          <col />
          <col class="actions" style="width: 20em;" />
        </colgroup>
        <thead>
          <tr>
            <th>#</th>
            <th>Modified</th>
            <th>Station</th>
            <th>Submitter</th>
            <th>Start time</th>
            <th>Contents</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <!-- generate your rows here, from view -->
        </tbody>
      </tea:sortable-table>

    In this example, we would need a view having the fields ``id``,
    ``modified``, ``station``, ``submitter`` and ``start_date``. We annotate the
    columns using the ``@name`` attribute (which is not in the output XML) to
    let the processor know which column has to deal with which field of the
    view.

    .. note::

       Spanning columns in the definitions is not supported.

    The sortable table processor creates ``h:a`` elements inside the ``h:th``
    elements for which a corresponding ``h:col`` element with ``@name``
    exists. The function of the links depend on whether the column is the column
    by which the data is currently ordered. If that is the case, the link will
    reverse ordering, otherwise the link will change the column by which is
    ordered to the column at which the link is placed, preserving the order
    direction.

    The current column additionally gets a ``h:div`` as child of the ``h:a``,
    which shows an order indicator and gets assigned the css class passed as
    *order_indicator_class*.

    The active columns ``h:col`` element also gets the *active_column_class*
    assigned.

    .. note::

       Contrary to most other elements, ``tea:sortable-table`` requires its
       attributes to be in the ``tea:`` namespace, to avoid conflicts with
       future HTML attributes.

    In the optional ``@tea:href`` attribute, it is possible to replace the
    standard implementation to create a URL for the routable ``@tea:routable``
    by custom means. The code in ``@tea:href`` is evaluated (use is only
    allowed in Unsafe safety modes) and must be a callable. The callable is
    passed the routable as first argument and ``view`` as keyword argument
    whenever a URL needs to be created, and it is expected that it returns a
    string containing the URL suitable to be put in a HTML href attribute.
    """

    xmlns = shared_ns

    def __init__(self,
                 safety_level=xsltea.SafetyLevel.conservative,
                 active_column_class=None,
                 order_indicator_class=None,
                 **kwargs):
        super().__init__(**kwargs)

        self._safety_level = safety_level

        self.active_column_class = active_column_class
        self.order_indicator_class = order_indicator_class

        self.attrhooks = {}
        self.elemhooks = {
            (str(self.xmlns), "sortable-table"): [self.handle_sortable_table]
        }

    def _col_handler(self, my_context, template, elem, context, offset):
        precode, elemcode, postcode = template.default_subtree(
            elem, context, offset)

        try:
            name = elem.attrib["name"]
        except KeyError as err:
            return precode, elemcode, postcode

        if self.active_column_class:
            classmod_ast = compile("""\
if _a.get_orderby_field() == _b:
    elem.set("class", _c + elem.get("class", ""))""",
                                   context.filename,
                                   "exec",
                                   ast.PyCF_ONLY_AST)
            classmod_ast = xsltea.template.replace_ast_names(classmod_ast, {
                "_a": my_context.pageobj_ast,
                "_b": name,
                "_c": "" if self.active_column_class is None \
                         else (str(self.active_column_class) + " ")
                }).body

            elemcode[-1:-1] = classmod_ast

        return precode, elemcode, postcode

    def _th_handler(self, my_context, template, elem, context, offset):
        sourceline = elem.sourceline or 0

        if offset not in my_context.named_columns:
            # not instrumented
            return template.default_subtree(elem, context, offset)

        name, _ = my_context.named_columns[offset]

        childfun_name = "children{}".format(offset)
        precode = template.compose_childrenfun(elem, context, childfun_name)
        postcode = []

        attr_precode, attr_elemcode, attrdict, attr_postcode = \
            template.compose_attrdict(elem, context)

        elemcode = compile("""\
elem = context.makeelement(_elem_tag, attrib=_attrdict)
elem.tail = _elem_tail
elem_a = etree.SubElement(elem, _xhtml_a)
if _page.get_orderby_field() == _name:
    elem_a.set(
        "href",
        _href(
            _viewobj,
            view=_page.with_orderby(
                new_direction=(
                 "asc"
                 if _page.get_orderby_dir() == "desc"
                 else "desc"))))
    elem_div = etree.SubElement(
        elem_a,
        _xhtml_div,
        attrib={
            "class": _order_indicator_class
        })
    elem_div.tail = _elem_text
    elem_div.text = "▲" if _page.get_orderby_dir() == "asc" else "▼"
else:
    elem_a.text = _elem_text
    elem_a.set(
        "href",
        _href(
            _viewobj,
            view=_page.with_orderby(new_fieldname=_name)))
utils.append_children(elem_a, _childfun())
yield elem""",
                           context.filename,
                           "exec",
                           ast.PyCF_ONLY_AST)
        elemcode = xsltea.template.ReplaceAstNames({
            "_elem_tag": elem.tag,
            "_attrdict": attrdict,
            "_elem_tail": elem.tail or "",
            "_page": my_context.pageobj_ast,
            "_name": name,
            "_xhtml_div": xhtml_ns.div,
            "_order_indicator_class": ("" if self.order_indicator_class is None
                                       else str(self.order_indicator_class)),
            "_childfun": ast.Name(childfun_name,
                                  ast.Load(),
                                  lineno=sourceline,
                                  col_offset=0),
            "_xhtml_a": xhtml_ns.a,
            "_elem_text": elem.text or "",
            "_viewobj": my_context.viewobj_ast,
            "_href": template.ast_get_stored(
                my_context.href_key,
                sourceline)
        }).visit(elemcode).body

        if precode:
            elemcode[-2:-2] = attr_elemcode
        else:
            elemcode[-2:-1] = attr_elemcode

        precode.extend(attr_precode)
        postcode.extend(attr_postcode)

        return precode, elemcode, postcode

    def handle_sortable_table(self, template, elem, context, offset):
        sourceline = elem.sourceline or 0
        try:
            pageobj = elem.attrib[self.xmlns.page]
            viewobj = elem.attrib[self.xmlns.routable]
            href_generator = elem.attrib.get(self.xmlns.href, None)
        except KeyError as err:
            raise ValueError(
                "Missing required attribute on tea:sortable-table: "
                "@tea:{}".format(str(err).split("}", 1)[1]))

        colgroup = elem.findall(xhtml_ns.colgroup)
        if len(colgroup) != 1:
            raise ValueError("tea:sortable-table requires exactly one colgroup")

        cols = list(colgroup[0].iter(xhtml_ns.col))

        named_columns = {}
        for i, col in enumerate(cols):
            try:
                name = col.attrib["name"]
            except KeyError:
                continue
            named_columns[i] = name, col

        my_context = Context()
        my_context.named_columns = named_columns
        my_context.pageobj_ast = compile(pageobj,
                                         context.filename,
                                         "eval",
                                         ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(my_context.pageobj_ast)
        my_context.viewobj_ast = compile(viewobj,
                                         context.filename,
                                         "eval",
                                         ast.PyCF_ONLY_AST).body
        self._safety_level.check_safety(my_context.viewobj_ast)

        if href_generator is not None:
            if self._safety_level != xsltea.safe.SafetyLevel.unsafe:
                raise ValueError("tea:href is not allowed in non-unsafe mode.")

            href_eval = compile(href_generator,
                                context.filename,
                                "eval",
                                ast.PyCF_ONLY_AST).body
            self._safety_level.check_safety(href_eval)
        else:
            href_eval = template.ast_get_href(sourceline)

        # allocate a storage key
        my_context.href_key = template.store(object())

        col_handler = functools.partial(
            self._col_handler,
            my_context)

        th_handler = functools.partial(
            self._th_handler,
            my_context)

        context.elemhooks.setdefault((str(xhtml_ns), "col"), []).insert(
            0, col_handler)
        context.elemhooks.setdefault((str(xhtml_ns), "th"), []).insert(
            0, th_handler)
        try:
            precode, elemcode, postcode = template.default_subtree(
                elem, context, offset)
        finally:
            del context.elemhooks[(str(xhtml_ns), "col")][0]
            del context.elemhooks[(str(xhtml_ns), "th")][0]

        elemcode[0].value.args[0] = ast.Str(
            xhtml_ns.table,
            lineno=sourceline,
            col_offset=0)

        elemcode[:0] = [
            ast.Assign(
                [
                    template.ast_get_stored(my_context.href_key,
                                            sourceline,
                                            ctx=ast.Store())
                ],
                href_eval,
                lineno=sourceline,
                col_offset=0)
        ]

        return precode, elemcode, postcode
