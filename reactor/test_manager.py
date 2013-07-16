from reactor.testing import harness
from reactor.loadbalancer.connection import LoadBalancerConnection
from reactor.zookeeper import paths

class TestManager(object):
    def test_find_loadbalancer_connection(self, scale_manager):
        # Default connection object should be None
        assert scale_manager._find_loadbalancer_connection() is not None

        # Test a couple of load balancer loading to ensure the manager finds the
        # correct modules.
        for lb in ['nginx', 'tcp', 'rdp', 'dnsmasq']:
            lbobj = scale_manager._find_loadbalancer_connection(lb)
            assert isinstance(lbobj, LoadBalancerConnection)
            assert lbobj.__module__ == 'reactor.loadbalancer.%s.connection' % lb

    def test_setup_loabalancer_connections(self, scale_manager, manager_config):
        # Ensure the manager loads all listed lbs from its config.
        manager_config.loadbalancers = ['tcp', 'rdp']

        scale_manager._setup_loadbalancer_connections(manager_config)
        assert isinstance(scale_manager.loadbalancers, dict)
        assert len(scale_manager.loadbalancers.items()) == 2
        for lb in manager_config.loadbalancers:
            assert scale_manager.loadbalancers.has_key(lb)

        # Ensure the manager correctly updates the lbs when the config changes.
        manager_config.loadbalancers = ['nginx']
        scale_manager._setup_loadbalancer_connections(manager_config)
        assert isinstance(scale_manager.loadbalancers, dict)
        assert len(scale_manager.loadbalancers.items()) == 1
        assert scale_manager.loadbalancers.has_key('nginx')

    def test_ensure_register_ip(self, scale_manager, reactor_zkclient, mock_endpoint):
        # 'Boot' our dummy instance.
        ip = '172.16.0.100' # Candidate IP.
        instance = harness.start_instance(scale_manager, mock_endpoint, ip=ip)

        with harness.ZkEvent(scale_manager.zk_conn, paths.new_ips(), expt_value=[ip]):
            # 'Register' by writing ip into zk, (as the external API call would).
            reactor_zkclient.record_new_ip_address(ip)

        assert ip in scale_manager.confirmed[mock_endpoint.name]
