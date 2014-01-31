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

  We have parts of this (see
  :class:`teapot.routing.selectors.AnnotationProcessor`), but there is room for
  much more and extensibility.

* Refactor form handling to metaclasses

* Regex path formatter

  This has some special difficulty, because unselecting is everything but trivial.

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

``xsltea`` todo
===============

Dedicated TODO file for the ``xsltea`` subproject:

* Implement ``NonEvilEvalProcessor``, which works much like the
  ``ExecProcessor``, but aims to be safe.

  This is most likely difficult and the only way I can think of to make this
  happen is to hook the parser and involve the user.

  We will have to obtain a parsed tree using the :mod:`ast` module. Afterwards,
  we can inspect and possibly modify the tree to our needs (inject hooks which
  perform safety checks or which proxy objects to block requests to unsafe
  attributes). When done, we can pass the tree to :func:`compile` to obtain a
  sanitized code object, which can be executed using :func:`eval` or
  :func:`exec`, respectively.

  Example::

    >>> import ast
    >>> tree = ast.parse("foo = bar")
    >>> tree.body[0].targets[0].id = "baz"
    >>> code = compile(tree, "", "exec")
    >>> globals_dict = {}
    >>> locals_dict = {"bar": 1}
    >>> exec(code, globals_dict, locals_dict)
    >>> print(locals_dict)
    {'bar': 1, 'baz': 1}

  That’s awesome, isn’t it? No, it’s just python \o/

  We can thus proxy return values from any expression and any names obtained
  from any scope so that we can apply restrictions on the access to these
  objects.

  Combined with decorators to denote safe attributes and methods on objects,
  this should yield a fairly safe language.
