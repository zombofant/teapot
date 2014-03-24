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

class TemplateProcessor:
    """
    This is the base class for template processors.

    Processor instances must have two attributes:

    .. attribute:: attrhooks

       A dictionary containing entries of the structure
       ``(xmlns, name): [attribute_hook]``. The ``xmlns`` must be a string
       refering to an XML namespace (or :data:`None`, to match on namespaceless
       attributes). `name` must be a string refering to the attributes local
       name or :data:`None` to match all attributes in the namespace.

       The signature and semantics of the ``attribute_hook`` functions are as
       follows:

       .. function:: attribute_hook(template, element, key, value, context) ->
                     (precode, elemcode, keycode, valuecode, postcode)

          The *template* is the template which is calling the hook. This is
          useful to make use of the helper functions provided by the
          :class:`Template` class.

          *element* is the :class:`lxml.etree._Element` instance to which the
          attribute having the name *key* (including the namespace in the usual
          etree notation) belongs. To save lookups, the *value* of the attribute
          is also included.

          *context* is a :class:`xsltea.template.Context` object which provides
          the processing context, including any hooks.

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
       ``(xmlns, name): [element_hook]``. The ``xmlns`` and ``name`` elements have
       the same semantics as for :attr:`attrhooks`, but they refer to element
       names instead of attribute names.

       The ``element_hook`` functions semantics are as follows:

       .. function:: element_hook(template, elemement, filename, offset) ->
                     (precode, elemcode, postcode)

          The *template* is the template which is calling the hook.

          *element* is the element which is being hooked. If you want the
          element to appear in the output tree, you must construct it in the
          *elemcode* and ``yield`` it from there.

          *context* is a :class:`xsltea.template.Context` object which provides
          the processing context, including any hooks.

          *offset* is the sibling index of the element you are operating on. Use
          that as a suffix for any names, except ``elem``, you create within any
          of the code arrays.

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



    """

    def global_postcode(self, template):
        """
        This function is called by the template and it is expected to supply an
        iterable of AST elements, which are supposed to be placed at the end of
        the document code.
        """
        return []

    def global_precode(self, template):
        """
        This function is called by the template and it is expected to supply an
        iterable of AST elements, which are supposed to be placed after the
        bootstrap and before any element code in the document code.
        """
        return []
