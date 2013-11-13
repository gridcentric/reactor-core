# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import sys
import uuid
import pytest
import atexit
import array

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

def cloud_submodules(include_all=False):
    return ["mock"]
def loadbalancer_submodules(include_all=False):
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
            if not hasattr(request, '__zk_finalizers'):
                request.addfinalizer(mock_zookeeper.dump)
                request.addfinalizer(mock_zookeeper.reset)
                setattr(request, '__zk_finalizers', True)
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

@fixture()
def zk_conn(request):
    """ A zookeeper connection. """
    from reactor.zookeeper.connection import ZookeeperConnection
    return ZookeeperConnection(servers=["mock"])

@fixture()
def zk_client(request):
    """ A zookeeper client. """
    from reactor.zookeeper.client import ZookeeperClient
    return ZookeeperClient(zk_servers=["mock"])

from reactor.zookeeper.objects import RawObject
from reactor.zookeeper.objects import JSONObject
from reactor.zookeeper.objects import BinObject
@fixture(params=[RawObject, JSONObject, BinObject])
def zk_object(request):
    """ A zookeeper object. """
    return request.param(zk_client(request), '/test/' + str(uuid.uuid4()))

@fixture()
def reactor(request):
    """ A Reactor client connection. """
    from reactor.objects.root import Reactor
    return Reactor(zk_client(request))

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
def managers(request, n=5):
    """ A collection of scale managers (default 5). """
    # Create N managers.
    from reactor.manager import ScaleManager
    ms = map(lambda x: ScaleManager(["mock"], name="manager-%d" % x), range(n))
    for m in ms:
        m.serve()

    # Ensure that all have synchronized.
    zk_conn(request).sync()

    return ms

@fixture()
def manager(request):
    """ A single scale manager. """
    return managers(request, n=1)[0]

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
    r = reactor(request)
    for name in names:
        # Save all with an empty configuration.
        r.endpoints().create(name, {})

    # Create the collection of endpoints.
    from reactor.endpoint import Endpoint
    endpoints = map(lambda x: Endpoint(r.endpoints().get(x)[0]), names)

    # Ensure all watches have fired to
    # synchronize manager's active state.
    zk_conn(request).sync()

    return endpoints

@fixture()
def endpoint(request):
    """ A single boring endpoint. """
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
