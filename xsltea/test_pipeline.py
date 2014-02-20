import io
import unittest

import lxml.etree as etree

import teapot.mime
import teapot.request

import xsltea.pipeline

class TestPipeline(unittest.TestCase):
    def test_chaining(self):
        pipe1 = xsltea.pipeline.Pipeline()
        pipe2 = xsltea.pipeline.Pipeline(chain_from=pipe1)
        with self.assertRaises(ValueError):
            pipe2.loader = ""

        pipe3 = xsltea.pipeline.Pipeline(
            chain_from=pipe2,
            chain_to=pipe1)

        pipe1.local_transforms.append("a")
        pipe1.local_transforms.append("b")

        pipe2.local_transforms.append("c")

        pipe3.local_transforms.append("d")

        pipe1.loader = "ldr"

        self.assertSequenceEqual(
            ["a", "b", "c", "d", "a", "b"],
            list(pipe3.iter_transforms()))

        self.assertSequenceEqual(
            ["a", "b", "c"],
            list(pipe2.iter_transforms()))

        self.assertSequenceEqual(
            ["a", "b"],
            list(pipe1.iter_transforms()))

        self.assertIs(
            pipe1.loader,
            pipe2.loader)

        self.assertIs(
            pipe1.loader,
            pipe3.loader)

class TestXMLPipeline(unittest.TestCase):
    def setUp(self):
        self.tree = etree.fromstring("""<?xml version="1.0"?>
<foo><bar /></foo>""")

    def _apply_transforms(self, pipeline, request, tree, args):
        transform_iter = pipeline.apply_transforms(request)
        _ = next(transform_iter)
        return transform_iter.send((tree, args))

    def test_default(self):
        pipeline = xsltea.pipeline.XMLPipeline()
        request = teapot.request.Request()
        result = self._apply_transforms(pipeline, request, self.tree, {})
        self.assertEqual("""<?xml version='1.0' encoding='utf-8'?>
<foo><bar/></foo>""".encode("utf-8"),
            result)

    def test_pretty_print(self):
        pipeline = xsltea.pipeline.XMLPipeline(pretty_print=True)
        request = teapot.request.Request()
        result = self._apply_transforms(pipeline, request, self.tree, {})
        self.assertEqual("""<?xml version='1.0' encoding='utf-8'?>
<foo>
  <bar/>
</foo>
""".encode("utf-8"),
            result)

    def test_strictness(self):
        pipeline = xsltea.pipeline.XMLPipeline()
        self.assertIn(
            None,
            pipeline.output_types)
        pipeline = xsltea.pipeline.XMLPipeline(strict=True)
        self.assertNotIn(
            None,
            pipeline.output_types)

class TestXHTMLPipeline(unittest.TestCase):
    def setUp(self):
        self.tree = etree.fromstring("""<?xml version="1.0"?>
<h:html xmlns:h="http://www.w3.org/1999/xhtml">
  <h:head>
    <h:title>foo</h:title>
  </h:head>
  <h:body />
</h:html>""")

    def _apply_transforms(self, pipeline, request, tree, args):
        transform_iter = pipeline.apply_transforms(request)
        _ = next(transform_iter)
        return transform_iter.send((tree, args))

    def test_auto_to_html(self):
        pipeline = xsltea.pipeline.XHTMLPipeline()
        request = teapot.request.Request(user_agent="Firefox/6.0")
        request.accepted_content_type = teapot.mime.Type.application_xhtml
        self.assertIn(
            teapot.request.UserAgentFeatures.no_xhtml,
            request.user_agent_info.features)

        result = self._apply_transforms(pipeline, request, self.tree, {})
        # the namespace should indeed not be there, no idea why it is there and
        # how to get rid of it
        self.assertEqual("""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>foo</title>
  </head>
  <body></body>
</html>""".encode("utf-8"),
            result)

    def test_full_xhtml(self):
        pipeline = xsltea.pipeline.XHTMLPipeline()
        request = teapot.request.Request(user_agent="Opera/0.0 Version/13.0")
        request.accepted_content_type = teapot.mime.Type.application_xhtml
        self.assertIn(
            teapot.request.UserAgentFeatures.prefixed_xhtml,
            request.user_agent_info.features)

        result = self._apply_transforms(pipeline, request, self.tree, {})
        self.assertEqual("""<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE html>
<h:html xmlns:h="http://www.w3.org/1999/xhtml">
  <h:head>
    <h:title>foo</h:title>
  </h:head>
  <h:body/>
</h:html>""".encode("utf-8"),
            result)

    def test_prefixless_xhtml(self):
        pipeline = xsltea.pipeline.XHTMLPipeline()
        request = teapot.request.Request(user_agent="Firefox/8.0")
        request.accepted_content_type = teapot.mime.Type.application_xhtml
        self.assertNotIn(
            teapot.request.UserAgentFeatures.prefixed_xhtml,
            request.user_agent_info.features)

        result = self._apply_transforms(pipeline, request, self.tree, {})
        self.assertEqual(
            """<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>foo</title>
  </head>
  <body/>
</html>""".encode("utf-8"),
            result)


class TestTransform(unittest.TestCase):
    def test_xsl_transform(self):
        xsl = """<xsl:stylesheet version="1.0"
        xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="xml" indent="no"/>

  <xsl:template match="foo">
    <bar>
      <xsl:attribute name="attr">
        <xsl:value-of select="$something" />
      </xsl:attribute>
    </bar>
  </xsl:template>
</xsl:stylesheet>"""

        xml = """<foo />"""

        xslfile = io.StringIO(xsl)
        template = xsltea.pipeline.XSLTransform(
            etree.XMLParser(),
            xslfile)

        tree = template.transform(
            etree.fromstring(xml),
            {"something": "'bar'"})
        self.assertEqual("bar", tree.getroot().tag)
        self.assertEqual("bar", tree.getroot().attrib["attr"])
