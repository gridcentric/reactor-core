"""
The generic load balancer interface.
"""
from reactor import utils
from reactor.config import SubConfig

import logging

import reactor.zookeeper.paths as paths

def get_connection(name, config, scale_manager):

    if name == "none" or name == "":
        return LoadBalancerConnection(name, scale_manager, config)

    lb_config = LoadBalancerConfig(config)
    lb_class = lb_config.loadbalancer_class()
    if lb_class == '':
        lb_class = "reactor.loadbalancer.%s.Connection" % (name)
    lb_conn_class = utils.import_class(lb_class)
    return lb_conn_class(name, scale_manager, config)

class LoadBalancerConfig(SubConfig):

    def loadbalancer_class(self):
        return self._get("class", '')

class LoadBalancerConnection(object):
    def __init__(self, name, scale_manager):
        self._name          = name
        self._scale_manager = scale_manager

    def clear(self):
        pass
    def redirect(self, url, names, other, manager_ips):
        pass
    def change(self, url, names, public_ips, manager_ips, private_ips):
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

class BackendIP(object):
    def __init__(self, ip, port=0, weight=1):
        self.ip     = ip
        self.port   = port
        self.weight = weight

class LoadBalancers(list):

    def clear(self):
        for lb in self:
            lb.clear()

    def redirect(self, url, names, other_url, manager_ips):
        for lb in self:
            lb.redirect(url, names, other_url, manager_ips)

    def change(self, url, names, public_ips, manager_ips, private_ips):
        for lb in self:
            lb.change(url, names, public_ips, manager_ips, private_ips)

    def save(self):
        for lb in self:
            lb.save()

    def metrics(self):
        # This is the only complex metric (that requires multiplexing).  We
        # combine the load balancer metrics by hostname, adding weights where
        # they are not unique.
        results = {}
        for lb in self:
            result = lb.metrics()
            for (host, metrics) in result.items():
                if not(host in results):
                    results[host] = metrics
                    continue

                for key in metrics:
                    (oldweight, oldvalue) = results[host][key]
                    (newweight, newvalue) = metrics[key]
                    weight = (oldweight + newweight)
                    value  = ((oldvalue * oldweight) + (newvalue * newweight)) / weight
                    results[host][key] = (weight, value)

        return results
