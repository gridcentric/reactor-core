"""
The generic load balancer interface.
"""

def get_connection(name, config, scale_manager):
    if name == "nginx":
        config_path = config.get("config_path", "/etc/nginx/conf.d")
        site_path = config.get("site_path", "/etc/nginx/sites-enabled")
        sticky_sessions = config.get("sticky_sessions", "false").lower() == "true"
        try:
            keepalive = int(config.get("keepalive", '0'))
        except:
            keepalive = 0
        from gridcentric.pancake.loadbalancer.nginx import NginxLoadBalancerConnection
        return NginxLoadBalancerConnection(config_path, site_path, sticky_sessions, keepalive)

    elif name == "dnsmasq":
        config_path = config.get("config_path", "/etc/dnsmasq.d")
        hosts_path = config.get("hosts_path", "/etc/hosts.pancake")
        from gridcentric.pancake.loadbalancer.dnsmasq import DnsmasqLoadBalancerConnection
        return DnsmasqLoadBalancerConnection(config_path, hosts_path, scale_manager)

    elif name == "none" or name == "":
        return LoadBalancerConnection()

    else:
        raise Exception("Unknown load balancer: %s" % name)

class LoadBalancerConnection(object):
    def clear(self):
        pass
    def change(self, endpoint, port, names, manager_ips, public_ips, private_ips):
        pass
    def save(self):
        pass
    def metrics(self):
        # Returns { host : (weight, value) }
        return {}

class LoadBalancers(list):
    def clear(self):
        for lb in self:
            lb.clear()
    def change(self, endpoint, port, names, manager_ips, public_ips, private_ips):
        for lb in self:
            lb.change(endpoint, port, names, manager_ips, public_ips, private_ips)
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
            for (host, value) in result.items():
                if not(host in results):
                    results[host] = value
                else:
                    (oldweight, oldvalue) = results[host]
                    (newweight, newvalue) = value
                    weight = (oldweight + newweight)
                    value = ((oldvalue * oldweight) + (newvalue * newweight)) / weight
                    results[host] = (weight, value)

        return results
