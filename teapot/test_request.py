import unittest

import teapot.request

class TestRequest(unittest.TestCase):

    def test_reconstruct_url(self):
        req = teapot.request.Request(
            servername="localhost",
            serverport="8080",
            local_path="/foo/bar")
        self.assertEqual(
            req.reconstruct_url(),
            "http://localhost:8080/foo/bar")

        req = teapot.request.Request(
            servername="localhost",
            serverport="8080",
            local_path="/foo/bar",
            scriptname="/api")
        self.assertEqual(
            req.reconstruct_url(),
            "http://localhost:8080/api/foo/bar")

        req = teapot.request.Request(
            servername="localhost",
            serverport="8080",
            local_path="/foo/bar",
            scriptname="/api",
            query_data={"k": "v"})
        self.assertEqual(
            req.reconstruct_url(),
            "http://localhost:8080/api/foo/bar?k=v")

        req = teapot.request.Request(
            servername="localhost",
            serverport="8080",
            local_path="/foo/bar",
            scriptname="/api",
            query_data={
                "k1": ["v1", "v2"],
                "k2": ["v3", "v4"]
            })
        url = req.reconstruct_url()
        prefix = "http://localhost:8080/api/foo/bar?"
        self.assertTrue(url.startswith(prefix))
        url = url[len(prefix):]
        parts = url.split("&")
        self.assertIn("k1=v1", parts)
        self.assertIn("k1=v2", parts)
        self.assertIn("k2=v3", parts)
        self.assertIn("k2=v4", parts)
