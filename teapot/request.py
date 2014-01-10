import copy

class RequestMethod:
    __init__ = None

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

class Request:
    def __init__(self,
                 method,
                 local_path,
                 scheme,
                 query_dict,
                 accept_info,
                 *,
                 original_request=None):
        self._original_request = original_request
        self._method = method
        self._path = local_path
        self._scheme = scheme
        self._query_dict = query_dict
        self._accept_info = accept_info

    def __deepcopy__(self, copydict):
        return Request(
            self._method,
            self._path,
            self._scheme,
            copy.deepcopy(self._query_dict, copydict),
            copy.deepcopy(self._accept_info, copydict),
            original_request=self._original_request)

    @property
    def accept_info(self):
        return self._accept_info

    @property
    def method(self):
        return self._method

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value):
        self._path = value

    @property
    def query_dict(self):
        return self._query_dict

    @property
    def scheme(self):
        return self._scheme
