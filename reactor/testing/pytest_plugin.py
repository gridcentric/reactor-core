import logging
import pytest

from reactor.testing import harness
from reactor.testing.mock_cloud import MockCloudConnection
from reactor.testing.mock_loadbalancer import MockLoadBalancerConnection

from reactor import manager
from reactor.zooclient import ReactorClient
from reactor.zookeeper import paths

context = {}

def hashrequest(request):
    return (request.function.__name__, request.cls)

@pytest.fixture
def scale_manager(request):
    client = ReactorClient([harness.LOCAL_ZK_ADDRESS])
    m = manager.ScaleManager(client, names=['127.0.0.1'])
    context[hashrequest(request)] = m
    m.serve()

    def stop_manager():
        m.clean_stop()
        client._disconnect()

    request.addfinalizer(stop_manager)
    return m

@pytest.fixture
def manager_config():
    return manager.ManagerConfig()

@pytest.fixture
def reactor_zkclient():
    return ReactorClient([harness.LOCAL_ZK_ADDRESS])

@pytest.fixture
def mock_endpoint(request):
    scale_manager = context[hashrequest(request)]
    name = request.function.__name__
    scale_manager.create_endpoint(name)
    endpoint = scale_manager.endpoints[name]
    endpoint.cloud_conn = MockCloudConnection()
    endpoint.lb_conn = MockLoadBalancerConnection()
    scale_manager.clouds["mock_cloud"] = endpoint.cloud_conn
    scale_manager.loadbalancers["mock_lb"] = endpoint.lb_conn
    return endpoint

@pytest.fixture(autouse=True)
def isolate_zookeeper_root(request):
    path = harness.make_zk_testroot(
        request.cls.__name__ + "." + request.function.__name__)
    logging.debug("Setting zookeeper root for test %s to %s" % \
                      (request.function.__name__, path))
    paths.update_root(path)

    def cleanup_zk_node():
        harness.zookeeper_recursive_delete(path)

    request.addfinalizer(cleanup_zk_node)
