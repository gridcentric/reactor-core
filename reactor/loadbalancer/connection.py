"""
The generic load balancer interface.
"""
import logging
import traceback

from reactor import utils
from reactor.config import Connection
from reactor.config import Config
import reactor.zookeeper.paths as paths

def get_connection(name, **kwargs):
    if not name:
        return LoadBalancerConnection(name=name, **kwargs)
    try:
        lb_class = "reactor.loadbalancer.%s.connection.Connection" % name
        lb_conn_class = utils.import_class(lb_class)
        return lb_conn_class(name=name, **kwargs)
    except:
        logging.error("Error loading loadbalancer %s: %s" % \
            (name, traceback.format_exc()))
        return LoadBalancerConnection(name=name, **kwargs)

class BackendIP(object):
    def __init__(self, ip, port=0, weight=1):
        self.ip = ip
        self.port = port
        self.weight = weight

class Locks(object):

    def __init__(self, name, scale_manager):
        self._name = name
        self._scale_manager = scale_manager

    def list_ips(self):
        return self._scale_manager.zk_conn.list_children(
                paths.loadbalancer_ips(self._name))

    def find_unused_ip(self, ips, data=''):
        locked = self.list_ips() or []
        for ip in ips:
            if not(ip in locked):
                if self.lock_ip(ip, data):
                    return ip
        return None

    def find_locked_ip(self, data):
        locked = self.list_ips() or []
        for ip in locked:
            if data == self.read_ip(ip):
                return ip
        return None

    def lock_ip(self, ip, data=''):
        return self._scale_manager.zk_conn.trylock(
                paths.loadbalancer_ip(self._name, ip),
                default_value=data)

    def update_ip(self, ip, data=''):
        return self._scale_manager.zk_conn.write(
                paths.loadbalancer_ip(self._name, ip),
                data)

    def read_ip(self, ip):
        return self._scale_manager.zk_conn.read(
                paths.loadbalancer_ip(self._name, ip))

    def forget_ip(self, ip):
        return self._scale_manager.zk_conn.delete(
                paths.loadbalancer_ip(self._name, ip))

    def forget_all(self):
        locked = self.list_ips() or []
        for ip in locked:
            self.forget_ip(ip)

class LoadBalancerConnection(Connection):

    def __init__(self, name, config=None, locks=None):
        self.locks = locks
        Connection.__init__(self, object_class="loadbalancer", name=name, config=config)

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
    def sessions(self):
        # If supported, returns { host : [ client, client, ... ] }
        return None
    def drop_session(self, backend, client):
        pass
    def start_params(self, config):
        return {}
    def cleanup_start_params(self, config, start_params):
        pass
    def cleanup(self, config, name):
        pass
