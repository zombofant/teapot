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

* Refactor form handling to metaclasses

* Regex path formatter

  This has some special difficulty, because unselecting is everything but trivial.

* Think about file splitting. I know that pythoneers tend to love large files,
  but I start to get a _bad_, uneasy feeling for the teapot/routing.py file.

* Template engines could use decorators to supply their meta-information to the
  routing engine (e.g. supported content types) and hook into the routing
  process. Example (assuming the template engine is called xsltea)::

    # further teapot decorators here
    @teapot.route("/", "/index")
    @xsltea.templated
    def index(self):
        # now the return protocol is determined by the template engine --
        # it must convert the returned values to one of the protocols supported
        # by teapot
        # assuming that the engine only requires a file name for a template and
        # a dict of arguments, it could look like this:

        return ("some_template_file.xsl",
                {"arg1": "value1", …})

* We need a convenient way to set HTTP-headers (and cookies) within routables
