import abc
import binascii
import copy
import logging
import random

import lxml.etree as etree

from .namespaces import \
    internal_noncopyable_ns, \
    internal_copyable_ns
from .transforms import PathResolver
from .utils import sortedlist

xml_parser = etree.XMLParser(ns_clean=True,
                             remove_blank_text=True,
                             remove_comments=True)

logger = logging.getLogger(__name__)

class _TreeFormatter:
    """
    Private helper class to lazily format a *tree* for passing to logging
    functions.
    """

    def __init__(self, tree):
        self._tree = tree

    def __str__(self):
        return str(etree.tostring(self._tree))

class TemplateTree:
    """
    lxml trees are wrapped in :class:`TemplateTree` instances to provide some
    extra functionallity.

    Most notabily, an identification scheme for elements is implemented, both
    with forced unique (``id``) and with shared identifiers (``name``), which
    can be used for different purposes.

    .. note::
       The choice of nomenclature, that is, ``id`` for the enforced-unique and
       ``name`` for the shared identifier, is reasoned in the same choice for of
       nomenclature in the HTML standard, which is what ``xsltea`` will mostly
       deal with.

    .. warning::
       To make sure that no naming conflicts occur, always use
       :meth:`deepcopy_subtree` to create a deep copy of a subtree of an
       :class:`TemplateTree`. That method will remove any non-copyable
       attributes, such as the ``id`` attribute in the new copy, making it safe
       for reuse in this or any other template tree.

    To associate a name or id with an element, use the following methods:

    .. method:: get_element_id

    .. method:: get_element_name

    To retrieve elements by their name or id, you can use

    .. method:: get_element_by_id

    .. method:: get_elements_by_name

    Copying a subtree must be done using this method, to ensure that noncopyable
    attributes are not accidentially preserved across copy operations:

    .. method:: deepcopy_subtree

    """

    namespaces = {"internalnc": str(internal_noncopyable_ns),
                  "internalc": str(internal_copyable_ns)}

    _element_id_rng = random.Random()
    _element_id_rng.seed()

    def __init__(self, tree):
        self.tree = tree

    def __deepcopy__(self, copydict):
        return TemplateTree(copy.deepcopy(self.tree, copydict))

    def _get_elements_by_attribute(self, base, attrname, elemid):
        return base.xpath(
            "descendant::*[@{} = '{}']".format(
                attrname, elemid),
            namespaces=self.namespaces)

    def _get_unique_element_attribute(self, attrname):
        while True:
            randbytes = self._element_id_rng.getrandbits(128).to_bytes(
                16, 'little')
            elemid = attrname+binascii.b2a_hex(randbytes).decode()
            if not self._get_elements_by_attribute(self.tree, attrname, elemid):
                return elemid

    def deepcopy_subtree(self, subtree):
        """
        Copy the given element *subtree* and all of its children using
        :func:`copy.deepcopy`. In addition to mere copying, all attributes from
        the noncopyable namespace (see
        :class:`~xsltea.namespaces.internal_noncopyable_ns`) are removed from
        the new copy.
        """
        copied = copy.deepcopy(subtree)
        for noncopyable_attr in copied.xpath("//@*[namespace-uri() = '"+
                                             str(internal_noncopyable_ns)+"']"):
            del noncopyable_attr.getparent().attrib[noncopyable_attr.attrname]
        return copied

    def get_element_by_id(self, id):
        """
        Return the element carrying the given *id* or raise :class:`KeyError` if
        the element does not exist.
        """
        try:
            return self.tree.xpath("//*[@internalnc:id = '"+id+"']",
                                   namespaces=self.namespaces).pop()
        except IndexError:
            raise KeyError(id) from None

    def get_elements_by_name(self, name, root=None):
        """
        Return all elemements inside *root* which carry the given *name*. If no
        elements match, an empty list is returned.

        If *root* is omitted or :data:`None`, the whole tree is searched.
        """
        return self._get_elements_by_attribute(
            (root if root is not None else self.tree),
            "internalc:name", name)

    def get_element_id(self, element):
        """
        Get the ``id`` of the *element*. The same rules as for
        :meth:`get_element_name` apply, except that the `id` is not copied when
        the element is within a subtree copied using :meth:`deepcopy_subtree`.
        """
        id = element.get(internal_noncopyable_ns.id)
        if id is not None:
            return id

        id = self._get_unique_element_attribute("id")
        element.set(internal_noncopyable_ns.id, id)

        return id

    def get_element_name(self, element):
        """
        Get the ``internal:name`` of the *element*. If the element does not have
        such a name, it is generated randomly and attached to the element.

        This can be used to identify elements, as ``id(element)`` is not safe
        (lxml creates and destroys python objects for elements arbitrarily)
        and there is no other reasonably safe way, as the tree might be mutated
        heavily at any time.

        Note that multiple elements may share the same name, if they have been
        duplicated. Also, elements may just vanish during processing. Your code
        must be able to cope with both cases.
        """
        name = element.get(internal_copyable_ns.name)
        if name is not None:
            return name

        name = self._get_unique_element_attribute("name")
        element.set(internal_copyable_ns.name, name)

        return name

class EvaluationTree(TemplateTree):
    def __init__(self, template):
        super().__init__(copy.deepcopy(template.tree))
        self._processors = {
            processor_cls: processor_instance.get_context(self)
            for processor_cls, processor_instance
            in template._processors.items()}

    def get_processor(self, processor_cls):
        return self._processors[processor_cls]

class Template(TemplateTree):
    """
    Wrap an lxml ``ElementTree`` *tree* as a template. The *tree* may be heavily
    modified during processing, thus, if you need the tree also for other
    purposes make sure to pass a deep copy.

    For debugging output, the *name* of the template is also used; if the
    template does not come from a file, use another distinct identifier, such as
    ``"<string>"``.

    .. attribute:: tree

       The ``TemplateTree`` which belongs to the template.

    .. attribute:: name

       Name of the source from which the template was created. This can be any
       opaque identifier. It should not be relied on any semantics of this.

    Processors might need access to other processors, which is provided via

    .. automethod:: get_processor

    In addition, the template provides means for processors to hook into the
    evaluation of the template, which is in fact the main mean to take part in
    evaluation. Two hooking methods are supplied, one hooking based on the
    elements name (thus, the hook is executed for all copies of the element if
    it is duplicated during evalation, e.g. by the
    :class:`~xsltea.safe.ForeachProcessor`) and one based on the elements id
    (which is not executed for copies and might not even be executed for the
    original element if duplicating takes place).

    .. automethod:: hook_element_by_id

    .. automethod:: hook_element_by_name

    The remaining methods are called by the engine. :meth:`preprocess` is called
    right after the template initialization and independent from a special
    evaluation of the template and :meth:`process` is called whenever the
    template is evaluated with specific arguments.

    An alternative way to instanciate a template is:

    .. automethod:: from_buffer
    """

    @classmethod
    def from_buffer(cls, buf, name, **kwargs):
        """
        Load a template from the given buffer or string *buf* (lxml will take
        care of converting a buffer to a string using the XML header).

        The *kwargs* are forwarded to the constructor.
        """
        return cls(etree.fromstring(buf, parser=xml_parser).getroottree(),
                   name)

    from_string = from_buffer

    def __init__(self, tree, name, **kwargs):
        super().__init__(tree, **kwargs)
        self.name = name
        self._processors_ordered = []
        self._processors = {}
        # the lists are sortedlists by default
        # maps { element_id => [(processor_cls, hook)] }
        self._id_hooked_elements = {}
        # maps { element_name => [(processor_cls, hook)] }
        self._name_hooked_elements = {}

    def _add_processor(self, processor_cls, *args, **kwargs):
        if processor_cls in self._processors:
            raise ValueError("{} already loaded in template {}".format(
                processor_cls, self))
        processor = processor_cls(self, *args, **kwargs)
        self._processors_ordered.append(processor)
        self._processors[processor_cls] = processor

    def _get_hooks(self, element):
        hooks = sortedlist(key=lambda x: x[0])
        try:
            elemid = element.attrib[internal_noncopyable_ns.id]
            logger.debug("looking up hooks for element id %s", elemid)
            hooks.update(self._id_hooked_elements[elemid])
        except KeyError:
            logger.debug("no id-based hooks for %s", element)
        try:
            elemname = element.attrib[internal_copyable_ns.name]
            logger.debug("looking up hooks for element name %s", elemname)
            hooks.update(self._name_hooked_elements[elemname])
        except KeyError:
            logger.debug("no name-based hooks for %s", element)
        return hooks


    def _has_hook(self, element):
        return (internal_copyable_ns.hooked in element.attrib or
                internal_noncopyable_ns.hooked in element.attrib)

    def _insert_hook(self, hook_dict, key, processor_cls, hook):
        logger.debug("inserting hook %s with key %s for processor %s",
                      hook, key, processor_cls)
        # not using setdefault here because sortedlist construction could be
        # expensive, at least it requires arguments and readability would suffer
        try:
            targetlist = hook_dict[key]
        except KeyError:
            targetlist = sortedlist(
                key=lambda x: x[0])
            hook_dict[key] = targetlist

        targetlist.add((processor_cls, hook))

    def _process_hook(self, template_tree, hooked_element, arguments):
        items = []
        logger.debug("running hooks for %s", hooked_element)
        # remove hooked flags
        try:
            del hooked_element.attrib[internal_noncopyable_ns.hooked]
        except KeyError:
            pass
        try:
            del hooked_element.attrib[internal_copyable_ns.hooked]
        except KeyError:
            pass
        for _, hook in self._get_hooks(hooked_element):
            logger.debug("running hook %r", hook)
            result = hook(template_tree, hooked_element, arguments)
            if result is None:
                continue
            result = list(result)

            # if the hook returns an iterable, we replace the hooked element by
            # the elements in the iterable
            parent = hooked_element.getparent()
            last_element = hooked_element.getprevious()
            pos = parent.index(hooked_element)
            del parent[pos]
            for item in result:
                if isinstance(item, str):
                    if last_element is None:
                        if parent.text is None:
                            parent.text = item
                        else:
                            parent.text += item
                    else:
                        if last_element.tail is None:
                            last_element.tail = item
                        else:
                            last_element.tail += item
                    continue
                last_element = item
                parent.insert(pos, item)
                items.append(item)
                pos += 1

            # in addition, there is no element which is hooked anymore, so we
            # can just return. tell the caller the element has vanished
            return items
        items.append(hooked_element)
        return items

    def get_processor(self, processor_cls):
        """
        Return the processor instance of the given processor class associated
        with this Template. If the processor has not been added to the template
        (via the :class:`Engine`), :class:`KeyError` is raised.
        """
        return self._processors[processor_cls]

    def hook_element_by_id(self, element, processor_cls, hook):
        """
        Add a hook to an *element*, idenitfied by its id. The *processor_cls*
        must be the class (not the object!) of the processor requesting that
        hook. It is used for ordering the hook execution so that BEFORE/AFTER
        relationships are fulfilled.
        """
        self._insert_hook(
            self._id_hooked_elements,
            self.get_element_id(element),
            processor_cls,
            hook)
        element.set(internal_noncopyable_ns.hooked, "")

    def hook_element_by_name(self, element, processor_cls, hook):
        """
        Add a hook to an *element*, identified by its name. For details on the
        arguments, see :meth:`hook_element_by_id`.

        The difference to hooking by id is that hooks are not preserved across
        tree copy operations performed by :meth:`deepcopy_subtree`.
        """
        self._insert_hook(
            self._name_hooked_elements,
            self.get_element_name(element),
            processor_cls,
            hook)
        element.set(internal_copyable_ns.hooked, "")

    def preprocess(self):
        for processor in self._processors_ordered:
            processor.preprocess()

    def process(self, arguments):
        """
        Process the template using the given dictionary of *arguments*.

        Return the result tree after all processors have been applied.
        """
        tree = EvaluationTree(self)
        root = tree.tree.getroot()

        if self._has_hook(root):
            logger.debug("root has hook")
            # process hook at root, afterwards search through the remaining hooks
            self._process_hook(tree, root, arguments)

        curr = root
        # search for hooked elements until done
        while True:
            logger.debug("current tree: %s", _TreeFormatter(tree.tree))
            try:
                next_hooked = root.xpath(
                    "descendant::*["
                    "@internalnc:hooked or @internalc:hooked][1]",
                    namespaces=self.namespaces).pop()
            except IndexError:
                # no further hooked elements
                logger.debug("no more hooked elements, returning")
                break

            logger.debug("next hooked element is at %s", next_hooked)
            self._process_hook(tree, next_hooked, arguments)

        # clear_element_ids(tree)
        return tree

class TemplateLoader(metaclass=abc.ABCMeta):
    """
    This is a base class to implement custom template loaders whose result is a
    tree format compatible to the default XML format.

    To subclass, several entry points are offered:

    .. automethod:: _load_template_etree

    .. automethod:: _load_template
    """

    def __init__(self, *sources, **kwargs):
        super().__init__(**kwargs)
        self._sources = list(sources)
        self._cache = {}
        self._processors = []
        self._resolver = PathResolver(*sources)
        self._parser = etree.XMLParser()
        self._parser.resolvers.add(self._resolver)

    def _add_processor(self, processor_cls, added, new_processors):
        if processor_cls in new_processors:
            return

        if processor_cls in added:
            raise ValueError("{} has recursive dependencies".format(
                processor_cls))

        added.add(processor_cls)
        for requires in processor_cls.REQUIRES:
                self._add_processor(requires, added, new_processors)

        new_processors.append(processor_cls)

    @abc.abstractmethod
    def _load_template_etree(self, buf, name):
        """
        This can be overwritten to provide an element tree object which
        represents the template contained in the buffer-compatible object *buf*
        obtained from a file (or other source) called *name*.
        """

    def _load_template(self, buf, name):
        """
        If more customization is required, this method can be overwritten to
        provdie a fully qualified template object (including all processors
        attached to this loader) from the buffer-compatible object in *buf*
        obtained from a source object called *name*.
        """
        tree = self._load_template_etree(buf, name)
        template = Template(tree, name)
        for processor in self._processors:
            template._add_processor(processor)
        template.preprocess()
        return template

    def add_processor(self, processor_cls):
        """
        Add a template processor class to the list of template processors which
        shall be applied to all templates loaded using this engine.

        This also recursively loads all required processor classes; if this
        leads to a circular require, a :class:`ValueError` is raised.

        Inserting a processor with :attr:`xsltea.processor.ProcessorMeta.BEFORE`
        restrictions is in the worst case (no restrictions apply) linear in
        amount of currently added processors.

        Drops the template cache.
        """
        if processor_cls in self._processors:
            return

        # delegate to infinite-recursion-safe function :)
        for required in processor_cls.REQUIRES:
            self.add_processor(required)

        new_index = None
        if processor_cls.BEFORE:
            # we can ignore AFTER here, because we, by default, insert at the
            # end.
            new_index = len(self._processors)
            for i, other_cls in enumerate(self._processors):
                if other_cls in processor_cls.BEFORE:
                    new_index = min(i, new_index)
                    break

        if new_index is not None:
            self._processors.insert(new_index, processor_cls)
        else:
            # no ordering restrictions found
            self._processors.append(processor_cls)

        # drop cache
        self._cache.clear()

    @property
    def processors(self):
        return self._processors

    def get_template(self, name):
        """
        Return the template identified by the given *name*. If the template has
        been loaded before, it might be retrieved from the cache. Otherwise, all
        sources are searched for templates and the first source to be able to
        provide the template will be used.

        The template is loaded and initialized with all currently registered
        template processors.
        """
        try:
            return self.cache[name]
        except KeyError:
            pass

        for source in self._sources:
            try:
                f = source.open(name)
                break
            except FileNotFoundError:
                pass
            except OSError as err:
                logging.warn(
                    "while searching for template %s: %s",
                    ame, err)
        else:
            raise FileNotFoundError(name)

        try:
            template = self._load_template(f.read())
        finally:
            f.close()

        self.cache[name] = template
        return template

class XMLTemplateLoader(TemplateLoader):
    """
    This is the default template loader for xsltea. It implements
    loading templates from XML and can be subclassed to process any other format
    which can either be converted into the default XML format.
    """

    def _load_template_etree(self, buf, name):
        tree = etree.fromstring(
            buf,
            parser=xml_parser).getroottree()
        return tree
