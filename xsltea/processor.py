"""
``xsltea.processor`` – Template processor plugins base
######################################################

Templates are processed using :class:`TemplateProcessor` instances. These
interpret the template contents and can be used to implement arbitrary
extensions.

.. autoclass:: TemplateProcessor
   :members:

"""

import abc
import functools

@functools.total_ordering
class ProcessorMeta(type):
    """
    This metaclass is used to keep the ordering and dependency attributes of the
    processor classes in sync.

    Classes with this metaclass (e.g. all classes inheriting from
    :class:`TemplateProcessor`) can use the following attributes:

    .. attribute:: REQUIRES

       This can be assigned an iterable of processor classes which are required
       by the processor. These processors will also be loaded by the
       :class:`xsltea.Engine` upon loading this processor.

    .. attribute:: AFTER

       This can be assigned an iterable of processor classes after which the
       current processor wants to be loaded.

    .. attribute:: BEFORE

       This can be assigned an iterable of processor classes before which the
       current processor wants to be loaded.

    .. note::
       All attributes must be created at class construction time. Later
       alterations are not allowed and can lead to strange behaviour including
       infinite loops.

    All attributes are available after class construction, even if not specified
    in the original class. The :attr:`AFTER` and :attr:`BEFORE` attributes are
    kept in sync with other definitions. That is, if you have a processor class
    `A` and another processor class `B` which specifies `A` in its `AFTER`
    attribute, `B` will show up in the `BEFORE` attribute of `A` afterwards.

    Note that mentioning a processor in :attr:`AFTER` will not make it being
    loaded by the :class:`Engine` automatically. The Before-After relation is
    orthogonal to the Requires-relation.

    The relationship established by :attr:`BEFORE` and :attr:`AFTER` is
    transitive.
    """

    @classmethod
    def _loopcheck(mcls, cls, attribute, saw_classes):
        if cls in saw_classes:
            raise ValueError("circular dependency in {} specification".format(
                attribute))

        saw_classes.add(cls)
        for other_cls in getattr(cls, attribute):
            mcls._loopcheck(other_cls, attribute, set(saw_classes))

    @property
    def REQUIRES(cls):
        return frozenset(cls.__REQUIRES)

    @property
    def AFTER(cls):
        return frozenset(cls.__AFTER)

    @property
    def BEFORE(cls):
        return frozenset(cls.__BEFORE)

    def __new__(mcls, name, bases, namespace):
        requires = set(namespace.get("REQUIRES", []))
        after = set(namespace.get("AFTER", []))
        before = set(namespace.get("BEFORE", []))

        namespace["_ProcessorMeta__REQUIRES"] = requires
        namespace["_ProcessorMeta__AFTER"] = after
        namespace["_ProcessorMeta__BEFORE"] = before

        cls = super().__new__(mcls, name, bases, namespace)

        for after_cls in list(after):
            after |= after_cls.__AFTER
        for before_cls in list(before):
            before |= before_cls.__BEFORE
        for after_cls in after:
            after_cls.__BEFORE |= cls.__BEFORE
            after_cls.__BEFORE.add(cls)
        for before_cls in before:
            before_cls.__AFTER |= cls.__AFTER
            before_cls.__AFTER.add(cls)

        mcls._loopcheck(cls, "BEFORE", set())
        mcls._loopcheck(cls, "REQUIRES", set())

        return cls

    def __hash__(cls):
        return type.__hash__(cls)

    def __lt__(cls, other):
        """
        This *cls* is _less than_ the *other*, if it has to be evaluated
        *before* the other class.
        """
        return other in cls.__BEFORE

    def __gt__(cls, other):
        """
        This *cls* is _greater than_ the *other*, if it has to be evaluated
        *after* the other class.
        """
        return other in cls.__AFTER

    # def __eq__(cls, other):
    #     """
    #     This *cls* is equal to the *other*, if *other* is scheduled neither
    #     before nor after the current *cls*.
    #     """
    #     return other not in cls.__BEFORE and other not in cls.__AFTER

class TemplateProcessor(metaclass=ProcessorMeta):
    """
    This is the base class for template processors.

    Processor instances must have two attributes:

    .. attribute:: attrhooks

       A dictionary containing entries of the structure
       ``(xmlns, name): attribute_hook``. The ``xmlns`` must be a string
       refering to an XML namespace (or :data:`None`, to match on namespaceless
       attributes). `name` must be a string refering to the attributes local
       name or :data:`None` to match all attributes in the namespace.

       The signature and semantics of the ``attribute_hook`` function are as
       follows:

       .. function:: attribute_hook(template, element, key, value, filename) ->
                     (precode, elemcode, keycode, valuecode, postcode)

          The *template* is the template which is calling the hook. This is
          useful to make use of the helper functions provided by the
          :class:`Template` class.

          *element* is the :class:`lxml.etree._Element` instance to which the
          attribute having the name *key* (including the namespace in the usual
          etree notation) belongs. To save lookups, the *value* of the attribute
          is also included.

          *filename* is the name of the template being processed. This should be
          passed to any :func:`compile` calls being issued by the hook.

          The return value is a tuple of several items:

          * *precode*: A list of AST statement objects (such as
            :class:`ast.Expr` and :class:`ast.Assign`) which are prepended to
            the code of the function describing the element (and all of its
            siblings).
          * *elemcode*: A list of AST statement objects, which are inserted
            after the element construction. Within these, the name `elem` refers
            to the element currently being dealt with. It is thus possible to
            include calls to `elem.set(key, value)` in that code.
          * *keycode* and *valuecode*: If no special handling is required, the
            key and value expressions for the attribute, as you would pass them
            to `elem.set()` can be passed here directly. If you set the
            attribute manually in *elemcode*, set this to :data:`None`. Setting
            the attribute using *keycode* and *valuecode* might be faster.
          * *postcode*: This code is appended to the end of the function
            describing the element (and all of its siblings.

    .. attribute:: elemhooks

       A dictionary containing entries of the structure
       ``(xmlns, name): element_hook``. The ``xmlns`` and ``name`` elements have
       the same semantics as for :attr:`attrhooks`, but they refer to element
       names instead of attribute names.

       The ``element_hook`` function semantics are as follows:

       .. function:: element_hook(template, elemement, filename, offset) ->
                     (precode, elemcode, postcode)

          The *template* is the template which is calling the hook.

          *element* is the element which is being hooked. If you want the
          element to appear in the output tree, you must construct it in the
          *elemcode* and ``yield`` it from there.

          *filename* is the name of the template being operated on. *offset* is
          the sibling index of the element you are operating on. Use that as a
          suffix for any names, except ``elem``, you create within any of the
          code arrays.

          The return value is a tuple of several items:
          * *precode*: A list of AST statement objects (such as
            :class:`ast.Expr` and :class:`ast.Assign`) which are prepended to
            the code of the function describing the element and all of its
            siblings. Use this to define a children function, if needed (see
            :meth:`~xsltea.template.Template.compose_childrenfun` for a utility
            doing that for you).
          * *elemcode*: A list of statements which create the element in a
            variable called ``elem`` and ``yield`` it.
          * *postcode*: A list of statements which is appended to the function
            defining the element and all of its sibilings.

          You can not only yield lxml elements, but also strings. Strings will
          be inserted as text where elements would be inserted as elements as
          children to the parent element.

          It is more efficient to add ``tail``-text directly to the element, if
          you are explicitly creating an element anyways.

          A ``makeelement`` function is available in the scope all of the code
          is evaluated. It is recommended to use that function instead of
          ``etree.Element`` to create elements.

    .. note::
       This class does in fact nothing. It had historical purpose though and it
       is thought that there might be future uses for having a common baseclass
       for all template processors.

       Please note that while inheriting from :class:`TemplateProcessor` is
       optional, using the metaclass :class:`ProcessorMeta` is required!

    """
