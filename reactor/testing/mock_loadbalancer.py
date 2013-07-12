from reactor.loadbalancer.connection import LoadBalancerConnection

class MockLoadBalancerConnection(LoadBalancerConnection):
    def __init__(self, config=None, locks=None):
        name = "mock_lb"
        LoadBalancerConnection.__init__(self, name, config=config, locks=locks)
