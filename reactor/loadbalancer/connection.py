"""
The generic load balancer interface.
"""
import re
import logging
import traceback

from reactor import utils
from reactor.config import Connection

def get_connection(name, **kwargs):
    if not name:
        return LoadBalancerConnection(name=name, **kwargs)
    try:
        lb_class = "reactor.loadbalancer.%s.connection.Connection" % name
        lb_conn_class = utils.import_class(lb_class)
        return lb_conn_class(name=name, **kwargs)
    except Exception:
        logging.error("Error loading loadbalancer %s: %s",
            name, traceback.format_exc())
        return LoadBalancerConnection(name=name, **kwargs)

class LoadBalancerConnection(Connection):

    """ No loadbalancer """

    # A map of all supported URLs.
    # It takes the form:
    #   regex => lambda match
    #
    # For example, a sensible http loadbalancer might have:
    #   "http://([a-zA-Z0-9]+[a-zA-Z0-9.]*)(:[0-9]+|)(/.*|)": \
    #        lambda m: (m.group(1), m.group(2), m.group(3))
    # These represents HOST, PORT (optional), PATH (optional).

    _SUPPORTED_URLS = {
        ".*" : lambda m: m.group(0)
    }

    def __init__(self, name, config=None, locks=None):
        self.locks = locks
        super(LoadBalancerConnection, self).__init__(
            object_class="loadbalancer", name=name, config=config)

    def url_info(self, url):
        if url is None:
            url = ""

        # Find the matching regex for this URL.
        for (regex, exp) in self._SUPPORTED_URLS.items():
            m = re.match(regex + "$", url)
            if m:
                return exp(m)

        # This URL is not supported.
        raise Exception("Invalid URL for loadbalancer.")

    def clear(self):
        pass

    def change(self, url, backends, config=None):
        if len(backends) != 0:
            raise NotImplementedError()

    def save(self):
        pass

    def metrics(self):
        # Returns { host : (weight, value) }
        return {}

    def sessions(self):
        # If supported, returns { host : [ client, client, ... ] }
        return {}

    def drop_session(self, client, backend):
        raise NotImplementedError()

    def start_params(self, config):
        return {}

    def cleanup_start_params(self, config, start_params):
        pass

    def cleanup(self, config, name):
        pass
