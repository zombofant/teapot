"""
SQLAlchemy utilities
####################

Teapot provides some utilities to better integrate with the popular
:mod:`sqlalchemy` database package.

Session management
==================

There is a :class:`~teapot.routing.Router` mixin which provides a ``dbsession``
attribute on the :class:`~teapot.request.Request` instance. For this it uses a
standard :class:`sqlalchemy.orm.session.sessionmaker`.

Creating queries through routing
================================

.. automodule:: teapot.sqlalchemy.dbview

"""

from . import dbview

class SessionMixin:
    def __init__(self, sessionmaker, **kwargs):
        super().__init__(**kwargs)
        self._sessionmaker = sessionmaker

    def pre_route_hook(self, request):
        super().pre_route_hook(request)
        request.dbsession = self._sessionmaker()

    def post_response_cleanup(self, request):
        request.dbsession.close()
        del request.dbsession
        super().post_response_cleanup(request)
