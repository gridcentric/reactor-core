from reactor.tests.pytest_plugin import fixture, zk_client

from reactor.objects.endpoint import Instances
from reactor.objects.endpoint import IPAddresses
from reactor.objects.endpoint import Sessions
from reactor.objects.endpoint import Log
from reactor.objects.endpoint import State

from reactor.zookeeper.objects import BinObject

@fixture()
def endpoint(request):
    from reactor.objects.endpoint import Endpoint
    return Endpoint(zk_client(request))

def test_state(endpoint):
    assert endpoint.state().current() == State.default
    assert endpoint.state().action("start") == State.running
    assert endpoint.state().current() == State.running

def test_log(endpoint):
    assert isinstance(endpoint.log(), Log)

def test_manager(endpoint):
    assert not endpoint.manager 
    endpoint.manager = "foo"
    assert endpoint.manager == "foo"

def test_metrics(endpoint):
    assert not endpoint.metrics
    endpoint.metrics = { "metric1" : [0.0, 1] }
    assert endpoint.metrics == { "metric1" : [0.0, 1] }
    assert not endpoint.custom_metrics
 
def test_custom_metrics(endpoint):
    assert not endpoint.custom_metrics
    endpoint.custom_metrics = { "metric1" : [0.0, 1] }
    assert endpoint.custom_metrics == { "metric1" : [0.0, 1] }
    assert not endpoint.metrics

def test_active(endpoint):
    assert not endpoint.active
    endpoint.active = [0, 1, 2, 3]
    assert endpoint.active == [0, 1, 2, 3]

def test_ip_metrics(endpoint):
    assert isinstance(endpoint.ip_metrics(), IPAddresses)

def test_instances(endpoint):
    assert isinstance(endpoint.instances(), Instances)

def test_decommissioned_instances(endpoint):
    assert isinstance(endpoint.decommissioned_instances(), Instances)

def test_marked_instances(endpoint):
    assert isinstance(endpoint.decommissioned_instances(), Instances)

def test_sessions(endpoint):
    assert isinstance(endpoint.sessions(), Sessions)
