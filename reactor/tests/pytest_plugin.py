import sys
import uuid
import pytest
import atexit

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

# Mock out the zookeeper module.
# This plugin will run before anything else. We ensure
# that all interfaces are normal, except the test cases
# will run with our stubbed out Zookeeper module.
from . import mock_zookeeper
sys.modules["zookeeper"] = mock_zookeeper

# Support standard fixtures here.
# This allows us to easily create properly configured
# scale managers, endpoints, etc.
# NOTE: Many of the fixtures just give you quick and easy
# access to the mock clouds, zookeeper, etc. so that you
# can easily assert the state matches expectations.

def fixture(**kwargs):
    pytest_fn = pytest.fixture(**kwargs)
    def _dec(fn):
        def _fn(request, *args, **kwargs):
            mangled_name = "%s__%s__%s" % (fn.__name__, str(args), str(kwargs))
            if hasattr(request, mangled_name):
                val = getattr(request, mangled_name)
            else:
                val = fn(request, *args, **kwargs)
                setattr(request, mangled_name, val)
            return val
        _fn.__name__ = fn.__name__
        _fn.__doc__ = fn.__doc__
        return pytest_fn(_fn)
    return _dec

def add_zk_finalizers(request):
    request.addfinalizer(mock_zookeeper.dump)
    request.addfinalizer(mock_zookeeper.reset)

@fixture()
def zk_conn(request):
    """ A zookeeper connection. """
    add_zk_finalizers(request)
    from reactor.zookeeper.connection import ZookeeperConnection
    return ZookeeperConnection(servers=["mock"])

@fixture()
def zk_client(request):
    """ A zookeeper client. """
    add_zk_finalizers(request)
    from reactor.zookeeper.client import ZookeeperClient
    return ZookeeperClient(zk_servers=["mock"])

from reactor.zookeeper.object import RawObject, JSONObject, BinObject
@fixture(params=[RawObject, JSONObject, BinObject])
def zk_object(request):
    """ A zookeeper object. """
    add_zk_finalizers(request)
    return request.param(zk_client(request), '/test/' + str(uuid.uuid4()))

@fixture()
def cloud(request):
    """ A mock cloud connection. """
    from mock_cloud import connection
    return connection.Connection("mock")

@fixture()
def loadbalancer(request):
    """ A mock loadbalancer connection. """
    from mock_loadbalancer import connection
    return connection.Connection("mock")

@fixture()
def client(request):
    """ A reactor client. """
    from reactor.zooclient import ReactorClient
    c = ReactorClient(zk_servers=["mock"])
    c._connect()
    return c

@fixture()
def scale_managers(request, n=5):
    """ A collection of scale managers (default 5). """
    # Create N managers.
    from reactor.manager import ScaleManager
    ms = map(lambda x: ScaleManager(["mock"], names=["manager-%d" % x]), range(n))
    for m in ms:
        m.serve()
    zk_conn(request).sync()
    return ms

@fixture()
def scale_manager(request):
    """ A single scale manager. """
    return scale_managers(request, n=1)[0]

@fixture()
def manager_config(request):
    """ An empty manager config. """
    from reactor.manager import ManagerConfig
    return ManagerConfig()

@fixture()
def endpoints(request, n=5):
    """ A collection on endpoints (default 5). """
    # Create N endpoints.
    names = map(lambda x: "endpoint-%d" % x, range(n))
    c = client(request)
    for name in names:
        c.endpoint_manage(name)
    zk_conn(request).sync()

    # Return the collection of endpoints.
    from reactor.endpoint import Endpoint
    return map(lambda x: Endpoint(c, x), names)

@fixture()
def endpoint(request):
    """ A single endpoint. """
    return endpoints(request, n=1)[0]

@fixture()
def endpoint_config(request):
    """ An empty endpoint config. """
    from reactor.endpoint import EndpointConfig
    return EndpointConfig()

# Enable debug logging.
import logging
from reactor.log import configure
configure(level=logging.DEBUG)
