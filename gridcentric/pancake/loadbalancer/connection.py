"""
The generic load balancer interface.
"""

def get_connection(name, config, scale_manager):
    if name == "nginx":
        from gridcentric.pancake.loadbalancer.nginx import NginxLoadBalancerConfig
        from gridcentric.pancake.loadbalancer.nginx import NginxLoadBalancerConnection
        return NginxLoadBalancerConnection(NginxLoadBalancerConfig(config))

    elif name == "dnsmasq":
        from gridcentric.pancake.loadbalancer.dnsmasq import DnsmasqLoadBalancerConfig
        from gridcentric.pancake.loadbalancer.dnsmasq import DnsmasqLoadBalancerConnection
        return DnsmasqLoadBalancerConnection(DnsmasqLoadBalancerConfig(config), scale_manager)

    elif name == "none" or name == "":
        return LoadBalancerConnection()

    else:
        raise Exception("Unknown load balancer: %s" % name)

class LoadBalancerConnection(object):
    def clear(self):
        pass
    def change(self, url, names, public_ips, private_ips):
        pass
    def save(self):
        pass
    def metrics(self):
        # Returns { host : (weight, value) }
        return {}

class BackendIP(object):
    def __init__(self, ip, port=0, weight=1):
        self.ip     = ip
        self.port   = port
        self.weight = weight

class LoadBalancers(list):

    def clear(self):
        for lb in self:
            lb.clear()

    def change(self, url, names, public_ips, private_ips):
        for lb in self:
            lb.change(url, names, public_ips, private_ips)

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
