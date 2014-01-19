import copy
import re

import teapot.mime

class Method:
    __init__ = None

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

class UserAgentFeatures:
    """
    Namespace for user agent features.

    .. attribute:: no_xhtml

       The user agent is known to advertise support for XHTML in the
       HTTP ``Accept`` headers, but does not actually support XHTML.

    .. attribute:: prefixed_xhtml

       Most user agents which advertise XHTML support (and mostly have
       it) have an issue with XHTML namespace prefixes (e.g.
       ``<h:html xmlns:h="http://www.w3.org/1999/xhtml" />``). If the
       user agent is known *not* to have problems with this, the
       *prefixed_xhtml* attribute is set.

       See also the
       `related bugreport on firefox <https://bugzilla.mozilla.org/show_bug.cgi?id=492933>`_.

    .. attribute:: html5

       The user agent is known to be able to deal with HTML5
       websites. This does not neccessarily imply full support, but
       CSS selectors on HTML5 elements will work properly.

    .. attribute:: is_mobile

       The user agent is a mobile web browser.

    .. attribute:: is_indexer

       The user agent is a known (search engine) indexer.

    .. attribute:: is_crawler

       The user agent is a known web crawler / designated downloader.

    .. attribute:: is_browser

       The user agent is a web browser.
    """

    __init__ = None

    no_xhtml = "!http://www.w3.org/1999/xhtml"
    prefixed_xhtml = "http://www.w3.org/1999/xhtml#with-prefixes"
    html5 = "http://www.w3.org/TR/html51/"
    is_mobile = ":is_mobile"
    is_crawler = ":is_crawler"
    is_indexer = ":is_indexer"
    is_browser = ":is_browser"
    is_feedreader = ":is_feedreader"

class UserAgentFamily:
    """
    Namespace for user agent families.

    .. attribute:: internet_explorer

       Microsoft® Internet Explorer™

    .. attribute:: firefox

       Mozilla Firefox

    .. attribute:: mozilla

       Other mozilla

    .. attribute:: opera

       Opera Web Browser

    .. attribute:: links

       Links

    .. attribute:: lynx

       Lynx

    .. attribute:: wget

       wget

    .. attribute:: chrome

       Google Chrome / Chromium

    .. attribute:: konqueror

       Konqueror (KDE) web browser

    .. attribute:: yahoo_slurp

       Yahoo search engine crawler

    .. attribute:: googlebot

       Google search engine crawler

    .. attribute:: unknown

       Unknown user agent

    """

    __init__ = None

    internet_explorer = ":ie"
    ie = internet_explorer
    firefox = ":firefox"
    mozilla = ":mozilla"
    opera = ":opera"
    safari = ":safari"
    links = ":links"
    lynx = ":lynx"
    wget = ":wget"
    chrome = ":chrome"
    yahoo_slurp = ":yahoo-slurp"
    konqueror = ":konqueror"
    googlebot = ":googlebot"
    msnbot = ":msnbot"
    seamonkey = ":seamonkey"
    yandexbot = ":yandexbot"
    ahrefsbot = ":ahrefsbot"
    speedy_spider = ":speedy-spider"
    sistrix_crawler = ":sistrix-crawler"
    rotfuchs = ":rotfuchs"
    rssowl = ":rssowl"
    epiphany = ":epiphany"
    askbot = ":askbot"
    exabot = ":exabot"
    seekbot = ":seekbot"
    libwww_perl = ":libwww-perl"
    bingbot = ":bingbot"
    w3m = ":w3m"
    blank = ":-"
    unknown = None

useragent_regexes = [
    (UserAgentFamily.googlebot,
     re.compile("Googlebot/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.googlebot,
     re.compile("Googlebot-Image/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.bingbot,
     re.compile("bingbot/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.ahrefsbot,
     re.compile("AhrefsBot/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.yandexbot,
     re.compile("YandexBot/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.yahoo_slurp,
     re.compile("Yahoo! Slurp/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.yahoo_slurp, re.compile("Yahoo! Slurp")),
    (UserAgentFamily.speedy_spider, re.compile("Speedy Spider")),
    (UserAgentFamily.sistrix_crawler, re.compile("SISTRIX Crawler")),
    (UserAgentFamily.msnbot,
     re.compile("msnbot/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.msnbot,
     re.compile("msnbot-media/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.konqueror,
     re.compile("Konqueror/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.chrome,
     re.compile("Chrome/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.internet_explorer,
     re.compile("MSIE (?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.firefox,
     re.compile("Firefox/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.firefox,
     re.compile("Gecko/[0-9]+\s+Firefox[0-9]+")),
    (UserAgentFamily.firefox,
     re.compile("Minefield/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.firefox,
     re.compile("Iceape/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.firefox,
     re.compile("Iceweasel/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.seamonkey,
     re.compile("SeaMonkey/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.safari,
     re.compile("Safari/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.opera,
     re.compile("Opera/([0-9.]+).*Version/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.opera,
     re.compile("Opera/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.lynx,
     re.compile("Lynx/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.links, re.compile("Links ")),
    (UserAgentFamily.w3m,
     re.compile("w3m/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.wget,
     re.compile("[Ww]get/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.rotfuchs, re.compile("Gecko Rotfuchs")),
    (UserAgentFamily.epiphany,
     re.compile("Epiphany/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.rssowl,
     re.compile("RSSOwl/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.askbot, re.compile("Ask Jeeves")),
    (UserAgentFamily.exabot,
     re.compile("Exabot/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.seekbot,
     re.compile("Seekbot/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.libwww_perl,
     re.compile("libwww-perl/(?P<version>[0-9]+(\.[0-9]+)?)")),
    (UserAgentFamily.blank, re.compile("^\s*-\s*$"))
]

useragent_classes = {
    UserAgentFamily.googlebot: UserAgentFeatures.is_indexer,
    UserAgentFamily.bingbot: UserAgentFeatures.is_indexer,
    UserAgentFamily.yahoo_slurp: UserAgentFeatures.is_indexer,
    UserAgentFamily.msnbot: UserAgentFeatures.is_indexer,
    UserAgentFamily.speedy_spider: UserAgentFeatures.is_crawler,
    UserAgentFamily.sistrix_crawler: UserAgentFeatures.is_crawler,
    UserAgentFamily.wget: UserAgentFeatures.is_crawler,
    UserAgentFamily.firefox: UserAgentFeatures.is_browser,
    UserAgentFamily.seamonkey: UserAgentFeatures.is_browser,
    UserAgentFamily.safari: UserAgentFeatures.is_browser,
    UserAgentFamily.opera: UserAgentFeatures.is_browser,
    UserAgentFamily.links: UserAgentFeatures.is_browser,
    UserAgentFamily.lynx: UserAgentFeatures.is_browser,
    UserAgentFamily.rotfuchs: UserAgentFeatures.is_browser,
    UserAgentFamily.chrome: UserAgentFeatures.is_browser,
    UserAgentFamily.ie: UserAgentFeatures.is_browser,
    UserAgentFamily.w3m: UserAgentFeatures.is_browser,
    UserAgentFamily.konqueror: UserAgentFeatures.is_browser,
    UserAgentFamily.yandexbot: UserAgentFeatures.is_indexer,
    UserAgentFamily.ahrefsbot: UserAgentFeatures.is_crawler,
    UserAgentFamily.epiphany: UserAgentFeatures.is_browser,
    UserAgentFamily.askbot: UserAgentFeatures.is_indexer,
    UserAgentFamily.rssowl: UserAgentFeatures.is_feedreader,
    UserAgentFamily.exabot: UserAgentFeatures.is_indexer,
    UserAgentFamily.seekbot: UserAgentFeatures.is_indexer,
}

useragent_html5_support = {
    "ie": 9.0,
    "firefox": 4.0,
    "chrome": 6.0,
    "safari": 5.0,
    "opera": 11.1
}

useragent_prefixed_xhtml_support = {
    "firefox": None,
    "opera": 12.0,
    "chrome": 20.0,
    "safari": None,
    "ie": None
}

def inspect_user_agent_string(user_agent_string):
    """
    Inspect the given *user_agent_string* and return a tuple giving
    information about the user agent:
    ``(family, version, features)``.

    The *family* is one of the attributes in
    :class:`UserAgentFamily`, designating the user agent family, while
    *version* is a float containing the version from the user agent
    string.

    *features* is a set of :class:`UserAgentFeatures` attributes,
    which have been determined conservatively, that is, only attributes
    which are known for sure (assuming the user agent string is
    legit) have been added.

    If *family* cannot be determined reliably, ``(None, None, set())`` is
    returned. If *version* cannot be determined reliably, it is set to
    :data:`None` and no version-specific features will be set.
    """

    features = set()

    for agentname, regex in useragent_regexes:
        match = regex.search(user_agent_string)
        if not match:
            continue

        groups = match.groupdict()
        try:
            version = float(groups["version"])
        except (ValueError, KeyError):
            version = None
        useragent = agentname
        break
    else:
        useragent = None
        version = None

    if useragent is None:
        return useragent, version, features

    try:
        features.add(useragent_classes[useragent])
    except KeyError:
        pass

    if useragent == UserAgentFamily.ie and version < 9:
        # thank you, microsoft, for your really verbose accept headers -
        # which do _not_ include an explicit mention of text/html, instead,
        # you just assume you can q=1.0 everything.
        features.add(UserAgentFeatures.no_xhtml)
    elif useragent == UserAgentFamily.chrome and version < 7:
        # but open browsers are not neccessarily better -- chromium with
        # version <= 6.0 sends:
        # application/xml;q=1.00, application/xhtml+xml;q=1.00, \
        # text/html;q=0.90, text/plain;q=0.80, image/png;q=1.00, */*;q=0.50
        # but is in fact unable to parse valid XHTML.
        features.add(UserAgentFeatures.no_xhtml)
    elif useragent == UserAgentFamily.firefox and version == 6:
        # this is google+ user agent. g+ seems to be unable to correctly
        # parse XHTML schema.org information (or metadata in general), which
        # screws up snippets.
        # see: http://stackoverflow.com/q/12426591/1248008
        # see: https://code.google.com/p/google-plus-platform/issues/detail?id=370
        features.add(UserAgentFeatures.no_xhtml)

    try:
        min_version = useragent_html5_support[useragent]
    except KeyError:
        pass
    else:
        if (    version is not None and
                min_version is not None and
                version >= min_version):
            features.add(UserAgentFeatures.html5)

    try:
        min_version = useragent_prefixed_xhtml_support[useragent]
    except KeyError:
        pass
    else:
        if (    version is not None and
                min_version is not None and
                version >= min_version):
            features.add(UserAgentFeatures.prefixed_xhtml)

    return useragent, version, features


class Request:
    @classmethod
    def construct_from_http(
            cls,
            request_method,
            path_info,
            url_scheme,
            query_data,
            input_stream,
            content_length,
            content_type,
            http_headers):
        """
        This is a forward-compatible way to construct a request object out of
        the information typically available from a CGI or WSGI environment.

        For details on the WSGI objects referred to here, see `PEP-3333
        <http://www.python.org/dev/peps/pep-3333/>`_.

        :param str request_method: WSGI ``REQUEST_METHOD`` equivalent
        :param str path_info: WSGI ``PATH_INFO`` equivalent
        :param str url_scheme: URL scheme used for the request (``http`` or
                               ``https``, typically)
        :param query_data: WSGI ``QUERY_STRING`` equivalent
        :type query_data: either a ``str`` or a dict mapping the keys to lists
                            of values
        :param input_stream: file-like object allowing access to the body of
                             the request sent by the client
        :type input_stream: file-like object
        :param content_length: the length of the request body
        :type content_length: something which is castable to int or :data:`None`
                              if unset
        :param content_type: WSGI ``CONTENT_TYPE`` equivalent
        :type content_type: a str containing the header or :data:`None` if unset
        :param iterable http_headers: an iterable yielding all other HTTP
                                      headers as tuples ``(header, value)``.
        :return: A fully specified :class:`Request` object.

        Any strings passed to this method must be proper unicode
        strings. Decoding must have been done by the web interface.
        """

        if not isinstance(query_data, dict):
            query_data = urllib.parse.parse_qs(query_data)

        # XXX: do we need this? can headers be meaningfully concatenated that
        # way?
        headers = teapot.mime.CaseFoldedDict()
        for header, new_value in http_headers:
            try:
                value = headers[header]
            except KeyError:
                headers[header] = new_value
            else:
                headers[header] = value + new_value

        try:
            charsets = teapot.accept.CharsetPreferenceList()
            charsets.append_header(headers["Accept-Charset"])
        except KeyError:
            charsets = teapot.accept.all_charsets()
            charsets.inject_rfc_values()

        try:
            contents = teapot.accept.AcceptPreferenceList()
            contents.append_header(headers["Accept"])
        except KeyError:
            contents = teapot.accept.all_content_types()

        try:
            languages = teapot.accept.LanguagePreferenceList()
            languages.append_header(headers["Accept-Language"])
        except KeyError:
            languages = teapot.accept.all_languages()

        try:
            if_modified_since_str = headers["If-Modified-Since"]
        except KeyError:
            if_modified_since = None
        else:
            try:
                if_modified_since = teapot.timeutils.parse_http_date(
                    if_modified_since_str)
            except ValueError as err:
                logger.warn("failed to parse If-Modified-Since header: %s", err)
                if_modified_since = None

        return cls(
            request_method,
            path_info,
            url_scheme,
            query_data,
            (
                contents,
                languages,
                charsets
            ),
            headers.get("User-Agent", ""),
            input_stream,
            if_modified_since=if_modified_since,
            raw_http_headers=headers)

    def __init__(self,
                 method,
                 local_path,
                 scheme,
                 query_data,
                 accept_info,
                 user_agent,
                 body_stream,
                 if_modified_since=None,
                 raw_http_headers=[]):
        self._method = method
        self._path = local_path
        self._scheme = scheme
        self._query_data = query_data
        self._user_agent_string = user_agent
        self._user_agent_info = inspect_user_agent_string(user_agent)
        self._accept_content, self._accept_language, self._accept_charset = \
            accept_info

        self.body_stream = body_stream
        self.raw_http_headers = raw_http_headers
        self.if_modified_since = if_modified_since

    @property
    def accept_charset(self):
        return self._accept_charset

    @property
    def accept_content(self):
        return self._accept_content

    @property
    def accept_info(self):
        return (self._accept_content,
                self._accept_language,
                self._accept_charset)

    @property
    def accept_language(self):
        return self._accept_language

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
    def query_data(self):
        return self._query_data

    @property
    def scheme(self):
        return self._scheme

    @property
    def user_agent(self):
        return self._user_agent_string

    @property
    def user_agent_info(self):
        return self._user_agent_info
