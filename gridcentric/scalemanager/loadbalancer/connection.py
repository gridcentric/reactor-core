

def get_connection(config_path):
    from gridcentric.scalemanager.loadbalancer.nginx import NginxLoadBalancerConnection
    return NginxLoadBalancerConnection(config_path)

class LoadBalancerConnection(object):
    pass

    def update(self, url, addresses):
        pass