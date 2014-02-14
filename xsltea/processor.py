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
    This is a base for namespace processors. Each namespace processor deals with
    XML elements and attributes from a specific namespace (or set of
    namespaces).

    It takes care of preparing and executing the namespaces effects in the
    template based on the arguments passed from the function invoking the
    template.

    Template processors should apply any hooks (see
    :meth:`~xsltea.Template.hook_element_by_id` and
    :meth:`~xsltea.Template.hook_element_by_name`) they need in the
    :meth:`preprocess` method, which is called upon creation of the template
    (i.e. once per template, not once per template evaluation). Hooks are called
    for each evaluation of the template.
    """

    def __init__(self, template, **kwargs):
        super().__init__(**kwargs)
        self._template = template

    def get_context(self, evaluation_template):
        return self

    def preprocess(self):
        """
        Preprocess the given *subtree*, if possible.
        """
