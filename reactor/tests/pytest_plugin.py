import sys
import pytest

# Ensure that the available clouds are only the basic
# no-op cloud and our mock cloud instance. Note that the
# both instances will track instances as global state,
# so we can instantiate the class and query separately.
# NOTE: This doesn't affect unit tests for those modules,
# this will only affect auto-discovery for managers, etc.

from . import mock_cloud
sys.modules["reactor.cloud.mock"] = mock_cloud
from . import mock_loadbalancer
sys.modules["reactor.loadbalancer.mock"] = mock_loadbalancer

def cloud_submodules():
    return ["mock"]
def loadbalancer_submodules():
    return ["mock"]

from reactor import submodules
submodules.cloud_submodules = cloud_submodules
submodules.loadbalancer_submodules = loadbalancer_submodules

# Support standard fixtures here.
# This allows us to easily create properly configured
# scale managers, endpoints, etc.
# NOTE: Many of the fixtures just give you quick and easy
# access to the mock clouds, zookeeper, etc. so that you
# can easily assert the state matches expectations.

@pytest.fixture
def zookeeper(request):
    from . import mock_zookeeper
    return mock_zookeeper.ZookeeperConnection()

@pytest.fixture
def cloud(request):
    from mock_cloud import connection
    return connection.Connection()

@pytest.fixture
def loadbalancer(request):
    from mock_loadbalancer import connection
    return connection.Connection()

@pytest.fixture
def client(request):
    from . import mock_zookeeper
    from reactor.zooclient import ReactorClient
    return ReactorClient(zk_class=mock_zookeeper.ZookeeperConnection)

@pytest.fixture
def scale_manager(request):
    from reactor.manager import ScaleManager
    c = client(request)
    m = ScaleManager(c)
    m.serve()
    return m

@pytest.fixture
def manager_config(request):
    from reactor.manager import ManagerConfig
    return ManagerConfig()
