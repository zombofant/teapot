"""
``xsltea.pipeline`` – A pipeline to process templates to a final format
#######################################################################

To use xsltea, you will need a pipeline. Don’t worry, it is easy to create
one. A quickstart method is implemented in :func:`xsltea.make_pipeline`.

.. autoclass:: Pipeline

More specialized pipelines for XML and HTML output formats are also available:

.. autoclass:: XMLPipeline

.. autoclass:: XHTMLPipeline

"""

import abc
import functools
import logging

import lxml.etree as etree

import teapot.accept
import teapot.errors
import teapot.request
import teapot.routing
import teapot.routing.selectors

logger = logging.getLogger(__name__)

class Pipeline:
    """
    A pipeline is a composite of a list of transforms. In addition, it can chain
    to other Pipeline pieces on both ends of the pipeline.

    If it does not chain on the start end, a loader can be specified to load
    templates as lxml.etree.ElementTree objects.

    If it does not chain on the end end, a dictionary mapping output types
    (e.g. :class:`teapot.mime.Type` instances) to callables taking a
    :class:`teapot.request.Request` instance and the lxml.etree.ElementTree and
    returning one of the formats defined in
    :ref:`teapot.routing.return_protocols`.

    If no loader is provided in the chain, the default loader applies.

    .. attribute:: local_transforms

       This attribute holds the list of transforms to apply to the output before
       forwarding it to the next template in the chain (or passing it to the
       output handler).

    """

    def __init__(self, *, chain_from=None, chain_to=None, **kwargs):
        super().__init__(**kwargs)
        self.local_transforms = []
        self._chain_from = None
        self._chain_to = None
        self._loader = None
        self._output_types = {}

        self.chain_from = chain_from
        self.chain_to = chain_to

    @staticmethod
    def _check_for_loop(pipeline, seen):
        if pipeline.chain_from is not None:
            if pipeline.chain_from in seen:
                raise ValueError("loop in pipeline definition")
            seen.add(pipeline.chain_from)
            pipeline._check_for_loop(pipeline.chain_from, seen)
        if pipeline.chain_to is not None:
            if pipeline.chain_to in seen:
                raise ValueError("loop in pipeline definition")
            seen.add(pipeline.chain_to)
            pipeline._check_for_loop(pipeline.chain_to, seen)

    @property
    def chain_from(self):
        return self._chain_from

    @chain_from.setter
    def chain_from(self, value):
        if value is not None:
            self._check_for_loop(value, set((self,)))
        self._chain_from = value

    @property
    def chain_to(self):
        return self._chain_to

    @chain_to.setter
    def chain_to(self, value):
        if value is not None:
            self._check_for_loop(value, set((self,)))
        self._chain_to = value

    @property
    def loader(self):
        if self._chain_from is not None:
            return self._chain_from.loader
        return self._loader

    @loader.setter
    def loader(self, value):
        if self._chain_from is not None:
            raise ValueError("cannot set loader: "
                             "loader is chained from another pipeline")
        self._loader = value

    @property
    def output_types(self):
        if self._chain_to is not None:
            return self._chain_to._output_types
        return self._output_types

    def iter_transforms(self):
        if self._chain_from is not None:
            yield from self._chain_from.iter_transforms()
        yield from self.local_transforms
        if self._chain_to is not None:
            yield from self._chain_to.iter_transforms()

    def iter_output_types(self):
        if self._chain_to is not None:
            yield from self._chain_to.iter_output_types()
        yield from self._output_types.keys()

    def _default_handler(self, request):
        raise teapot.errors.make_response_error(
            406, "{} content type not supported".format(
                request.accepted_content_type))

    def _find_handler_for_content_type(self, accepted_content_type):
        try:
            return self.output_types[accepted_content_type]
        except KeyError:
            try:
                return self.output_types[None]
            except KeyError:
                return self._default_handler

    def apply_transforms(self, request):
        """
        Apply the whole pipeline, including output formatting, to the given
        *tree*, using the information from the original *request*.
        """

        handler = iter(self._find_handler_for_content_type(
            request.accepted_content_type)(request))

        tree, arguments = yield handler.send(None)
        for transform in self.iter_transforms():
            tree = transform.transform(tree, arguments)

        yield handler.send(tree)

    def _decorated_process(self,
                           arguments,
                           template,
                           request,
                           decorated_iter):
        template_args = dict(arguments)
        response = next(decorated_iter)

        transform_iter = iter(self.apply_transforms(request))
        content_type = next(transform_iter)
        response.content_type = content_type
        yield response

        user_template_args, user_transform_args = next(decorated_iter)
        template_args.update(user_template_args)
        tree = template.process(template_args, request=request)

        yield transform_iter.send((tree, user_transform_args))

    def _decorated(self, __arguments, __callable, __template_name, __request,
                   *args, **kwargs):
        template = self.loader.get_template(__template_name)
        return self._decorated_process(
            __arguments,
            template,
            __request,
            iter(__callable(*args, **kwargs)))

    def _decorated_variable_template(self, __arguments, __callable, __request,
                                     *args, **kwargs):
        decorated_iter = iter(__callable(*args, **kwargs))
        template_name = next(decorated_iter)
        template = self.loader.get_template(template_name)

        return self._decorated_process(
            __arguments,
            template,
            __request,
            decorated_iter)

    def _post_process_decorated(self, decorated, callable):
        decorated.__name__ = callable.__name__
        decorated.__qualname__ = callable.__qualname__
        decorated.__annotations__.update(callable.__annotations__)
        decorated = teapot.routing.make_routable([])(decorated)
        info = teapot.getrouteinfo(decorated)
        info.selectors.append(
            teapot.routing.selectors.content_type(
                *self.output_types.keys()))
        return decorated

    def with_template(self, template_name, arguments=None):
        if arguments is None:
            arguments = {}

        def decorator(callable):
            decorated_delegate = functools.partial(
                self._decorated,
                arguments,
                callable,
                template_name)
            def decorated(*args,
                          _Pipeline__xsltea_request_object: teapot.request.Request,
                          **kwargs):
                return decorated_delegate(__xsltea_request_object, *args, **kwargs)
            return self._post_process_decorated(decorated, callable)
        return decorator

    def with_variable_template(self, arguments=None):
        if arguments is None:
            arguments = {}

        def decorator(callable):
            decorated_delegate = functools.partial(
                self._decorated_variable_template,
                arguments,
                callable)

            def decorated(*args,
                          _Pipeline__xsltea_request_object: teapot.request.Request,
                          **kwargs):
                return decorated_delegate(__xsltea_request_object,
                                          *args, **kwargs)
            return self._post_process_decorated(decorated, callable)
        return decorator

class XMLPipeline(Pipeline):
    """
    A :class:`Pipeline` subclass which offers a raw xml output format. The input
    document can be any valid XML document.

    If *strict* is :data:`True`, a ``406 Not Acceptable`` error is raised if
    the client does not accept xml documents. This is not recommended in
    general, as XML documents can have very diverse meanings (e.g. SVG is also
    XML, but has a different MIME type).

    If *strict* is :data:`False`, pipelines using this pipeline as end pipeline
    will act as a catchall with regards to content negotiation!

    .. attribute:: pretty_print

       If set to true, the output will be pretty-printed.

       .. warning::
          In some document types, this may alter the semantics of the output
          compared to the input! Use with care.

       .. note::
          Pretty printed output might be considerably larger than
          non-pretty-printed. To avoid unneccessary overhead, use pretty
          printing only for debug purposes.

    """

    _preferences = [
        teapot.accept.MIMEPreference("application", "xml", q=1.0),
        teapot.accept.MIMEPreference("text", "xml", q=0.9),
    ]

    def __init__(self, *, strict=False, pretty_print=False, **kwargs):
        super().__init__(**kwargs)
        self._strict = strict
        self.pretty_print = pretty_print

        self._output_types = {
            teapot.mime.Type.application_xml: self._negotiate,
            teapot.mime.Type("text", "xml"): self._negotiate
        }

        if not strict:
            self._output_types[None] = self._negotiate

    def _tostring(self, tree, charset, **kwargs):
        etree.cleanup_namespaces(tree)
        return etree.tostring(
            tree,
            encoding=charset,
            xml_declaration=True,
            pretty_print=self.pretty_print,
            **kwargs)

    def _negotiate_charset(self, request):
        charsets = request.accept_charset.get_sorted_by_preference()
        for charset in charsets:
            charset = charset.value
            if charset is None:
                charset = "utf-8"
                break
        else:
            charset = "latin1"

        return charset

    def _negotiate(self, request):
        content_type = (request.accepted_content_type or
                        teapot.mime.Type.application_xml)
        charset = self._negotiate_charset(request)
        tree = yield content_type.with_charset(charset)
        yield self._tostring(tree, charset)

class XHTMLPipeline(XMLPipeline):
    """
    A :class:`Pipeline` subclass which offers all html-ish output formats and
    expects the input to be a valid XHTML document.

    The *strict* argument works the same as for the
    :class:`XMLPipeline`. However, the default document type generated will be
    HTML.

    Depending on the clients support, different documents will be generated. A
    full-featured, XHTML compatible client will get a normal XHTML
    document. Most XHTML clients however cannot deal with namespace prefixes,
    which is why they get a prefixless version of the XHTML document.

    All other clients get a plain HTML Strict document generated from the XHTML
    document.
    """

    _preferences = [
        teapot.accept.MIMEPreference("application", "xhtml+xml", q=1.0),
        teapot.accept.MIMEPreference("text", "html", q=0.9),
        teapot.accept.MIMEPreference("application", "xhtml", q=0.85),
        teapot.accept.MIMEPreference("text", "xhtml", q=0.85),
    ]

    _remove_prefixes_transform = etree.XSLT(etree.fromstring(
"""<xsl:stylesheet version="1.0"
        xmlns="http://www.w3.org/1999/xhtml"
        xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="xml" indent="no"/>

    <!-- identity transform for everything else -->
    <xsl:template match="/|comment()|processing-instruction()|*">
        <xsl:copy>
          <xsl:apply-templates select="@*|node()" />
        </xsl:copy>
    </xsl:template>

    <xsl:template match="@*">
        <xsl:copy />
    </xsl:template>

    <!-- remove NS from XHTML elements -->
    <xsl:template match="*[namespace-uri() = 'http://www.w3.org/1999/xhtml']">
        <xsl:element name="{local-name()}">
          <xsl:apply-templates select="@*|node()" />
        </xsl:element>
    </xsl:template>

    <!-- remove NS from XHTML attributes -->
    <xsl:template match="@*[namespace-uri() = 'http://www.w3.org/1999/xhtml']">
        <xsl:attribute name="{local-name()}">
          <xsl:value-of select="." />
        </xsl:attribute>
    </xsl:template>
</xsl:stylesheet>"""))

    def __init__(self, *, strict=True, html_version=5, **kwargs):
        super().__init__(strict=strict, **kwargs)

        self._output_types = {
            teapot.mime.Type.text_html: self._negotiate,
            teapot.mime.Type.application_xhtml: self._negotiate,
            # incorrect / deprecated MIME types for xhtml
            teapot.mime.Type("application", "xhtml"): self._negotiate,
            teapot.mime.Type("text", "xhtml"): self._negotiate,
            None: self._negotiate
        }

        if not strict:
            self._output_types[None] = self._negotiate

        if html_version == 4:
            self._xhtml_version_args = {
                "doctype": """<!DOCTYPE html
    PUBLIC "-//W3C//DTD XHTML 1.1//EN"
    "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">"""
            }
            self._html_version_args = {
                "doctype": """<!DOCTYPE HTML
    PUBLIC "-//W3C//DTD HTML 4.01//EN"
    "http://www.w3.org/TR/html4/strict.dtd">""",
                "method": "html"
            }

        elif html_version == 5:
            self._xhtml_version_args = {
                "doctype": "<!DOCTYPE html>",
            }
            self._html_version_args = dict(self._xhtml_version_args)
            self._html_version_args["method"] = "html"
        else:
            raise ValueError("Unsupported HTML version: {}".format(html_version))

    def _as_full_xhtml(self, tree, charset, **kwargs):
        kwargs.update(self._xhtml_version_args)
        return self._tostring(
            tree,
            charset,
            **kwargs)

    def _as_prefixless_xhtml(self, tree, charset, **kwargs):
        return self._as_full_xhtml(
            self._remove_prefixes_transform.apply(tree),
            charset,
            **kwargs)

    def _as_html(self, tree, charset, **kwargs):
        kwargs.update(self._html_version_args)
        # TODO: do we want to raise if non-xhtml elements are encountered, as a
        # safeguard?
        return self._tostring(
            self._remove_prefixes_transform.apply(tree),
            charset,
            **kwargs)

    def _negotiate(self, request):
        features = request.user_agent_info.features
        if teapot.request.UserAgentFeatures.no_xhtml in features:
            # no XHTML support, no matter what
            transform = self._as_html
            content_type = teapot.mime.Type.text_html
        else:
            if (    request.accepted_content_type is None or
                    "xhtml" not in request.accepted_content_type.subtype):
                transform = self._as_html
                content_type = teapot.mime.Type.text_html
            else:
                transform = self._as_full_xhtml
                content_type = teapot.mime.Type.application_xhtml

        if transform == self._as_full_xhtml:
            if teapot.request.UserAgentFeatures.prefixed_xhtml not in features:
                transform = self._as_prefixless_xhtml

        charset = self._negotiate_charset(request)

        tree = yield content_type.with_charset(charset)

        yield transform(tree, charset)

class PathResolver(etree.Resolver):
    def __init__(self, *sources, prefix="xsltea:"):
        super().__init__()
        self._sources = sources
        self._prefix = prefix
        self._parser = etree.XMLParser()
        self._parser.resolvers.add(self)

    def get_filelike(self, filename, binary=True):
        for source in self._sources:
            try:
                return source.open(filename, binary=binary)
            except FileNotFoundError as err:
                continue
            except OSError as err:
                logger.warn("while searching for xslt dependency %s: %s",
                            filename, err)
                continue
        else:
            raise FileNotFoundError(filename)

    def resolve(self, url, pubid, context):
        if url.startswith(self._prefix):
            logger.debug("resolving %s", url)
            filename = url[len(self._prefix):]
            return self.resolve_file(self.get_filelike(filename, binary=True))

class Transform(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def transform(self, tree, arguments):
        return tree

class XSLTransform(Transform):
    def __init__(self, parser, filelike):
        self._xslt = etree.XSLT(etree.parse(filelike, parser=parser))

    def transform(self, tree, arguments):
        return self._xslt.apply(tree, **arguments)

class TransformLoader:
    def __init__(self, *sources, **kwargs):
        super().__init__(**kwargs)
        self._resolver = PathResolver(*sources)

    def load_transform(self, name, cls=XSLTransform):
        return cls(self._resolver._parser,
                   self._resolver.get_filelike(name))
