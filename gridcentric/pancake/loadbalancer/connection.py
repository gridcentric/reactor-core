#!/usr/bin/env python

def get_connection(name, config):
    if name == "nginx":
        config_path = config.get("config_path", "/etc/nginx/conf.d")
        site_path = config.get("site_path", "/etc/nginx/sites-enabled")
        from gridcentric.pancake.loadbalancer.nginx import NginxLoadBalancerConnection
        return NginxLoadBalancerConnection(config_path, site_path)
    else:
        raise Exception("Unknown load balancer: %s" % name)

class LoadBalancerConnection(object):
    def clear(self):
        pass
    def change(self, url, addresses):
        pass
    def save(self):
        pass
    def metrics(self, url):
        # Returns { key : (weight, value) }
        return (0.0, {})
