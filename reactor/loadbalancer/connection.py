"""
The generic load balancer interface.
"""
import logging
import traceback

from reactor import utils
from reactor.config import Connection
from reactor.config import Config
import reactor.zookeeper.paths as paths

def get_connection(name, config, scale_manager):
    if not name:
        return LoadBalancerConnection(name, config, scale_manager)

    try:
        lb_class = "reactor.loadbalancer.%s.Connection" % name
        lb_conn_class = utils.import_class(lb_class)
        return lb_conn_class(name, config, scale_manager)
    except:
        logging.error("Unable to load loadbalancer: %s" % traceback.format_exc())
        return LoadBalancerConnection(name, config, scale_manager)

class BackendIP(object):
    def __init__(self, ip, port=0, weight=1):
        self.ip = ip
        self.port = port
        self.weight = weight

class LoadBalancerConnection(Connection):

    def __init__(self, name, config=None, scale_manager=None):
        Connection.__init__(self, object_class="loadbalancer", name=name, config=config)
        self._scale_manager = scale_manager

    def clear(self):
        pass
    def redirect(self, url, names, other, config=None):
        pass
    def change(self, url, names, ips, config=None):
        pass
    def save(self):
        pass
    def metrics(self):
        # Returns { host : (weight, value) }
        return {}

    # FIXME: The following functions provide a wrapper around the ScaleManager
    # to access shared per-IP metadata. These functions belong in a better
    # location than here, but don't necessary belong as simple member functions
    # of the ScaleManager itself (as they require a name and other data). They
    # will remain here for the time-being, but as they evolve, they should be
    # moved to a new more appropriate location / abstraction.

    def _list_ips(self):
        return self._scale_manager.zk_conn.list_children(
                paths.loadbalancer_ips(self._name))

    def _find_unused_ip(self, ips, data=''):
        locked = self._list_ips() or []
        for ip in ips:
            if not(ip in locked):
                if self._lock_ip(ip, data):
                    return ip
        return None

    def _lock_ip(self, ip, data=''):
        return self._scale_manager.zk_conn.trylock(
                paths.loadbalancer_ip(self._name, ip),
                default_value=data)

    def _update_ip(self, ip, data=''):
        return self._scale_manager.zk_conn.write(
                paths.loadbalancer_ip(self._name, ip),
                data)

    def _read_ip(self, ip):
        return self._scale_manager.zk_conn.read(
                paths.loadbalancer_ip(self._name, ip))

    def _forget_ip(self, ip):
        return self._scale_manager.zk_conn.delete(
                paths.loadbalancer_ip(self._name, ip))
