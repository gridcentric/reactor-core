from reactor.loadbalancer.connection import LoadBalancerConnection

class Connection(LoadBalancerConnection):

    def __init__(self, *args, **kwargs):
        LoadBalancerConnection.__init__(self, *args, **kwargs)
