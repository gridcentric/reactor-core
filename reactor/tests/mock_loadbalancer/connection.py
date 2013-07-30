from reactor.loadbalancer.connection import LoadBalancerConnection

class Connection(LoadBalancerConnection):

    """ Mock loadbalancer connection. """

    def __init__(self, *args, **kwargs):
        super(Connection, self).__init__(*args, **kwargs)
