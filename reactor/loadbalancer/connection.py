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
    lb_class = "reactor.loadbalancer.%s.connection.Connection" % name
    lb_conn_class = utils.import_class(lb_class)
    return lb_conn_class(name=name, **kwargs)

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

    def __init__(self,
        name,
        config=None,
        zkobj=None,
        this_ip=None,
        error_notify=None):

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

    def change(self, url, backends, config=None):
        """
        Specify a backend mapping in the loadbalancer.
        """
        if len(backends) != 0:
            raise NotImplementedError()

    def save(self):
        """
        Save current set of specified mappings.
        """
        pass

    def dropped(self, ip):
        pass

    def metrics(self):
        """
        Returns metrics as a dictionary --
            { "host:port" : (weight, value) }
        """
        return {}

    def pending(self):
        """
        Return pending sesisons as a dictionary --
            { "url" : count }
        """
        return {}

    def sessions(self):
        """
        Return active sessions as a dictionary --
            { "host:port" : [ client, client, ... ] }
        """
        return {}

    def drop_session(self, client, backend):
        raise NotImplementedError()

    def start_params(self, config):
        """
        Get a dictionary of start params for an instance.
        """
        return {}

    def cleanup_start_params(self, config, start_params):
        """
        Cleanup the given start params (when start fails).
        """
        pass

    def cleanup(self, config, name):
        """
        Cleanup the given instance.
        """
        pass
