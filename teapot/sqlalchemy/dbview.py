"""

.. autoclass:: dbview

.. autoclass:: View
"""

import abc
import copy
import functools
import operator

import teapot.routing.selectors
import teapot.forms
import teapot.html

from datetime import datetime, timedelta

__all__ = [
    "dbview",
    "subquery"
]

FIELDNAME_KEY = "f"
OPERATOR_KEY = "o"
VALUE_KEY = "v"

datetime_formats = [
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%MZ",
    "%Y-%m-%dT%H:%M",
]

operators = {
    "endswith",
    "startswith",
    "like",
    "contains",
    "notlike",
    "notin_",
    "in_",
    "__le__",
    "__lt__",
    "__eq__",
    "__ne__",
    "__ge__",
    "__gt__",
}

order_operators = {
    "__le__", "__lt__", "__eq__", "__ne__", "__ge__", "__gt__"}

type_mapping = {
    datetime: (
        lambda **kwargs: teapot.html.DateTimeField(
            teapot.html.DateTimeMode.Full,
            "datetime",
            **kwargs),
        order_operators),
    int: (
        lambda **kwargs: teapot.html.IntField(**kwargs),
        order_operators),
    str: (
        lambda **kwargs: teapot.html.TextField(**kwargs),
        operators - {"notin_", "in_"}),
    bool: (
        lambda **kwargs: teapot.html.CheckboxField(**kwargs),
        {"__eq__", "__ne__"}),
}

def descriptor_for_type(name, python_type, **kwargs):
    try:
        field_constructor, operators = type_mapping[python_type]
    except KeyError:
        raise ValueError("python type {} not mapped; provide an entry in the"
                         " teapot.sqlalchemy.dbview.type_mapping"
                         " dict".format(python_type))

    descriptor = field_constructor(**kwargs)
    return descriptor, operators

def one_of_descriptor(fieldname,
                      valid_values,
                      error=None,
                      default=None):
    if error is None:
        error = "Not a valid value. Use one of {}".format(
            ", ".join(str(value) for value in sorted(valid_values)))

    descriptor = teapot.html.EnumField(
        options=list(valid_values),
        default=default)
    return descriptor

class dynamic_rows(teapot.forms.CustomRows):
    def __init__(self, fieldname_key, fieldclasses):
        super().__init__()
        self._fieldname_key = fieldname_key
        self._fieldclasses = fieldclasses

    def instanciate_row(self, rows, request, subdata):
        try:
            fieldname = subdata[self._fieldname_key][0]
            fieldclass = self._fieldclasses[fieldname]
        except (IndexError, KeyError):
            return None

        rows.append(fieldclass(request=request, post_data=subdata))

class RowBase(teapot.forms.Row):
    pass

class View(teapot.forms.Form):
    """
    A :class:`View` object represents a slice of data, filtered, ordered and
    limited according to the parameters provided in a query. Instances of
    :class:`View` are provided to routables decorated with :class:`dbview`.

    Objects of this class behave approximately immutable. This means, any
    changes to attributes should happen using the provided methods and return
    new objects. This is to simplify unrouting.
    """

    _VALID_OBJECT_MODES = ["fields", "primary", "objects"]

    def __init__(self, dbsession, request=None, **kwargs):
        super().__init__(request=request, **kwargs)
        self.dbsession = dbsession
        self.request = request
        self._query = None

    @property
    def query(self):
        if self._query is not None:
            return self._query

        dbsession = self.dbsession
        objects = [self._primary_object]
        self._itermap = None
        if self._objects == "fields":
            self._itermap = lambda x: x[1:]
        elif self._objects == "primary":
            pass
        elif self._objects == "objects":
            objects += [
                obj
                for _, obj in self._supplemental_objects]

        fieldmap = {}
        joins = []
        for obj in self._supplemental_objects:
            try:
                join_mode, obj = obj
            except TypeError as err:
                join_mode = "join"
            joins.append((join_mode, obj))

        for fieldname, field, typehint in self._fields:
            if isinstance(field, lazy_node):
                subquery = field._evaluate(dbsession).subquery()
                field = getattr(subquery.c, fieldname)
                joins.append(("outerjoin", subquery))
            if self._objects == "fields":
                objects.append(field)
            fieldmap[fieldname] = field

        query = dbsession.query(*objects)
        for join in joins:
            jointype = join[0]
            args = join[1:]
            query = getattr(query, jointype)(*args)

        for filterrow in getattr(self, self._filter_key):
            field = fieldmap[filterrow.f]
            query = query.filter(
                getattr(field, filterrow.o)(filterrow.v))

        if self._custom_filter is not None:
            query = self._custom_filter(self.request, query)

        total = query.count()
        if self._itemsperpage > 0:
            total_pages = (total+(self._itemsperpage-1)) // self._itemsperpage
        else:
            total_pages = 1

        query = query.order_by(
            getattr(
                fieldmap[getattr(self, self._orderfield_key)],
                getattr(self, self._orderdir_key))())

        offset = (getattr(self, self._pageno_key)-1)*self._itemsperpage
        if total < offset:
            offset = (total_pages-1)*self._itemsperpage
        if offset < 0:
            offset = 0
        query = query.offset(offset)

        if self._itemsperpage > 0:
            length = min(total - offset, self._itemsperpage)
            query = query.limit(self._itemsperpage)
            setattr(self, self._pageno_key, (offset // self._itemsperpage)+1)
        else:
            length = total

        self._query = query
        self._length = length
        self._offset = offset
        self._total = total
        self._total_pages = total_pages

        return self._query

    @property
    def length(self):
        self.query
        return self._length

    @property
    def offset(self):
        self.query
        return self._offset

    @property
    def total(self):
        self.query
        return self._total

    @property
    def total_pages(self):
        self.query
        return self._total_pages

    def __deepcopy__(self, copydict):
        result = super().__deepcopy__(copydict)
        # invalidate the query cache
        result._query = None
        return result

    def get_pageno(self):
        """
        Return the page number this view points to.
        """
        return getattr(self, self._pageno_key)

    def get_orderby_dir(self):
        """
        Return the direction in which this view is ordered (either ``"asc"`` or
        ``"desc"``).
        """
        return getattr(self, self._orderdir_key)

    def get_orderby_field(self):
        """
        Return the field with respect to which this view is
        ordered.
        """
        return getattr(self, self._orderfield_key)

    def __len__(self):
        """
        Return the amount of entries provided by iterating over this view.
        """
        return self.length

    def __iter__(self):
        """
        Iterate over all items returned by this view (that is, all items on this
        page).
        """
        # we need to fetch query first, for _itermap to initialize
        query = self.query
        if self._itermap is None:
            return iter(query)
        else:
            return iter(map(self._itermap, query))

    def at_page(self, new_pageno):
        """
        Create and return a new view which is equal to this view, except that it
        points to a different page number.
        """
        result = copy.deepcopy(self)
        setattr(result, self._pageno_key, int(new_pageno))
        return result

    def with_orderby(self, new_fieldname=None, new_direction=None):
        """
        Create and return a new view which is equal to this view, but uses a
        different ordering.

        The new view uses the given *new_fieldname* as a field (or the current
        one, if *new_fieldname* is :data:`None`) and the *new_direction* as
        direction (or the current one, if *new_direction* is :data:`None`) for
        ordering.
        """
        result = copy.deepcopy(self)

        if new_fieldname is None and new_direction is None:
            return result

        if new_fieldname is not None:
            setattr(result, self._orderfield_key, new_fieldname)
        if new_direction is not None:
            setattr(result, self._orderdir_key, new_direction)

        return result

    def without_filters(self):
        """
        Create and return a new view which is equal to this view, but with all
        filters removed.


        .. warning::

           See the warning at :class:`View`.
        """
        result = copy.deepcopy(self)
        getattr(result, self._filter_key).clear()
        return result

def _create_row_class_for_field(fieldname, field, type_hint=None):
    """
    Create a filter row class for a field with name *fieldname* and object
    *field*. Use the *type_hint* if available, otherwise auto-detect the type
    from ``field.type.python_type``.

    Return the newly created class.
    """

    value_descriptor, operators = descriptor_for_type(
        VALUE_KEY,
        type_hint or field.type.python_type)
    namespace = {
        FIELDNAME_KEY: one_of_descriptor(
            FIELDNAME_KEY,
            [fieldname],
            error="Field name must match exactly"),
        OPERATOR_KEY: one_of_descriptor(
            OPERATOR_KEY,
            operators,
            error="Operator not supported for this field",
            default="__eq__"),
        VALUE_KEY: value_descriptor
    }

    return teapot.forms.RowMeta(
        "Row_"+fieldname,
        (RowBase,),
        namespace)


def make_form(
        primary_object,
        fields,
        *,
        supplemental_objects=[],
        autojoin=True,
        pageno_key="p",
        orderfield_key="ob",
        orderdir_key="d",
        filter_key="f",
        name="View",
        default_orderfield=None,
        default_orderdir="asc",
        objects="fields",
        itemsperpage=25,
        custom_filter=None):
    """
    Create a :class:`View` descandant for a specific use case.

    The database query produced by the instances of this class is a select on
    *primary_object*. The query queries for the given list of *fields*, which
    must be tuples of the following form: ``(name, field, type_hint)``. In this
    tuple, *name* is a unique (in this class) name for the field, *field* is the
    sqlalchemy Column object (or any selectable sqlalchemy expression). If
    *field* does not provide type information (read: does not have a
    ``type.python_type`` attribute), you have to provide a *type_hint* pointing
    to the python type which shall be used to deal with the fields
    values. Otherwise, you can leave the *type_hint* set to :data:`None`.

    If additional objects are required (e.g. explicit joins), these can be
    specified in the *supplemental_objects* list. These are never returned in
    the result and only used to set up the joins in sqlalchemy. If *autojoin* is
    :data:`True`, the code tries to guess the required *supplemental_objects*
    from the *fields* given, by adding each table once.

    *default_orderfield* and *default_orderdir* provide defaults for ordering,
    if the user hasn’t specified ordering. The *default_orderfield* must be a
    string referring to one of the field names from *fields*.

    *pageno_key*, *orderfield_key*, *orderdir_key* and *filter_key* define the
    query keys which are used to transfer the query information.

    *name* is the name of the class which will be created.

    *itemsperpage* is the amount of items returned in one pagination step.

    The *objects* parameter determines which objects are returned in the
    iterable. There are three supported values:

    * ``"fields"`` (the default) provides the fields specified in the *fields*
      array, and nothing more.
    * ``"primary"`` provides the *primary_object* instance associated with the
      row.
    * ``"objects"`` provides the *primary_object* alongside with the (possibly
      automatically detected) *supplemental_objects*.

    *custom_filter* can be a callable which is called on the final query object,
    before any limiting and ordering is applied. It must return a new query
    object to which limiting and ordering will be applied and which will be used
    to retrieve the data. The callable receives the *request* passed to the form
    on construction time as first, and the current query as second argument.

    Applying this decorator creates a :class:`teapot.forms.Form` which holds all
    the fields required to configure ordering, pagination and optionally
    filtering. Upon selecting, an instance of this form is created and, if that
    is succesful, passed to the routed function via *destarg*. For unselecting,
    such a form instance is converted into query arguments.

    The methods available on all forms created by this decorator are documented
    in :class:`View`.
    """

    if objects not in View._VALID_OBJECT_MODES:
        raise ValueError("{} is not a valid value for objects argument".format(
            objects))

    if autojoin and not supplemental_objects:
        # generate supplemental_objects by inspecting the fields
        supplemental_objects = list(set(
            field.class_
            for field_name, field, type_hint in fields
            if (hasattr(field, "class_") and
                field.class_ is not primary_object and
                not isinstance(field.class_, lazy_node))))

    # detect which fields are filterable by checking whether they have a
    # type.python_type attribute
    filterable_fields = list(filter(
        lambda x: x[2] or (hasattr(x[1], "type") and
                           hasattr(x[1].type, "python_type")),
        fields))

    # names for all valid fields
    field_names = frozenset(
        field_name
        for field_name, _, _ in filterable_fields)

    # map field names to types
    fieldclasses = {
        field_name: _create_row_class_for_field(
            field_name, field, type_hint)
        for field_name, field, type_hint in filterable_fields}


    # finally, the namespace for the :class:`View` descendant we’re about to
    # create
    namespace = {
        # “active” :class:`teapot.forms.Form` fields
        orderfield_key: one_of_descriptor(
            orderfield_key,
            field_names,
            default=default_orderfield),
        orderdir_key: one_of_descriptor(
            orderdir_key,
            {"asc", "desc"},
            default=default_orderdir),
        pageno_key: descriptor_for_type(
            pageno_key,
            int,
            default=1)[0],
        filter_key: dynamic_rows(
            FIELDNAME_KEY, fieldclasses),

        # the supplemental information required to create the query
        "_supplemental_objects": supplemental_objects,
        "_fields": fields,
        "_primary_object": primary_object,
        "_filter_key": filter_key,
        "_custom_filter": staticmethod(custom_filter),
        "_itemsperpage": itemsperpage,
        "_orderfield_key": orderfield_key,
        "_orderdir_key": orderdir_key,
        "_pageno_key": pageno_key,
        "_objects": objects
    }

    ViewForm = teapot.forms.Meta(
        name,
        (View,),
        namespace)

    return ViewForm

class dbview(teapot.routing.selectors.Selector):
    """
    A routing selector which is used to create a database query from query
    arguments.

    The selector uses the given *ViewForm*, which should have been created
    through :func:`make_form`. The *ViewForm* is populated during routing and
    passed to the routable via the argument whose name is given in *destarg*.
    """

    def __init__(self, ViewForm, *, destarg="view", **kwargs):
        super().__init__(**kwargs)
        self._ViewForm = ViewForm
        self._destarg = destarg

    def select(self, request):
        dbsession = request.original_request.dbsession
        try:
            view = self._ViewForm(dbsession,
                                  request=request,
                                  post_data=request.query_data)
        except ValueError:
            return False


        request.kwargs[self._destarg] = view
        return True

    def unselect(self, request):
        dbsession = request.original_request.dbsession
        try:
            view = request.kwargs.pop(self._destarg)
        except KeyError:
            view = self._ViewForm(dbsession)
        dest = request.query_data

        dest[view._pageno_key] = [str(getattr(view, view._pageno_key))]
        dest[view._orderfield_key] = [str(getattr(view, view._orderfield_key))]
        dest[view._orderdir_key] = [str(getattr(view, view._orderdir_key))]

        for i, row in enumerate(getattr(view, view._filter_key)):
            prefix = "{}[{}].".format(view._filter_key, i)
            dest[prefix+FIELDNAME_KEY] = [
                str(getattr(row, FIELDNAME_KEY))]
            dest[prefix+OPERATOR_KEY] = [
                str(getattr(row, OPERATOR_KEY))]
            value = getattr(row, VALUE_KEY)
            dest[prefix+VALUE_KEY] = [
                getattr(type(row), VALUE_KEY).to_field_value(row, "text")
            ]

    def __call__(self, callable):
        result = super().__call__(callable)
        result.dbview = self
        return result

    def new_view(self,
                 dbsession,
                 **simple_filters):
        view = self._ViewForm(dbsession)
        filter_rows = getattr(view, view._filter_key)
        for fieldname, value in simple_filters.items():
            try:
                cls = self._ViewForm.f._fieldclasses[fieldname]
            except KeyError:
                raise ValueError("Field `{}' is not filterable".format(
                    fieldname))

            row = cls()
            setattr(row, FIELDNAME_KEY, fieldname)
            setattr(row, OPERATOR_KEY, "__eq__")
            setattr(row, VALUE_KEY, value)
            filter_rows.append(row)

        return view

class lazy_node:
    def __init__(self, onlazy):
        super().__init__()
        self._onlazy = onlazy

    def _gettarget(self, on):
        if self._onlazy is not None:
            return self._onlazy._evaluate(on)
        else:
            return on

    def __getattr__(self, name):
        if name.startswith("_"):
            return self.__dict__[name]
        return lazy_operator(self, operator.attrgetter(name))

    def __call__(self, *args, **kwargs):
        return lazy_call(self, *args, **kwargs)

class lazy_call(lazy_node):
    def __init__(self, onlazy, *args, **kwargs):
        super().__init__(onlazy)
        self._args = args
        self._kwargs = kwargs

    def _evaluate(self, on):
        return self._gettarget(on)(*self._args, **self._kwargs)

class lazy_operator(lazy_node):
    def __init__(self, onlazy, operator):
        super().__init__(onlazy)
        self._operator = operator

    def _evaluate(self, on):
        return self._operator(self._gettarget(on))

def subquery(*args, **kwargs):
    """
    Support for subqueries in dbviews is implemented using this class. You can
    pass it arbitrary arguments and retrieve arbitrary members, which in turn
    will be callable. Nothing will be evaluated until the query is actually
    created (that is, at routing time).
    """

    return lazy_call(
        lazy_operator(None, operator.attrgetter("query")),
        *args,
        **kwargs)
