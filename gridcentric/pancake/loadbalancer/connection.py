#!/usr/bin/env python

def get_connection(config_path):
    from gridcentric.pancake.loadbalancer.nginx import NginxLoadBalancerConnection
    return NginxLoadBalancerConnection(config_path)

class LoadBalancerConnection(object):
    pass

    def update(self, url, addresses):
        pass
