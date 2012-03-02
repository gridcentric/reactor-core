#!/usr/bin/env python

def get_connection(config_path):
    from gridcentric.pancake.loadbalancer.nginx import NginxLoadBalancerConnection
    return NginxLoadBalancerConnection(config_path)

class LoadBalancerConnection(object):
    def clear(self):
        pass
    def change(self, url, addresses):
        pass
    def save(self):
        pass
    def metrics(self, url):
        return {}
