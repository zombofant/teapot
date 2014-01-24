Todo
####

This is the developers Todo file. Feel free to inspect and start hacking on any
point you like to modify.

* Use function annotations to pass some arguments in the router. Example::

    @teapot.route("/")
    def index(request: teapot.Request):
        pass

  This style should make the router replace the *request* argument with the
  original request sent by the client.

* POST data processing (including file upload, limiting)

  * Normal fields should be accessible like query data (but with their own
    decorator, do not reuse :class:`teapot.routing.query` for that), ideally
    already decoded into unicode objects
  * Uploaded files should be accessible as ``bytes`` objects, also through the
    decorator.
