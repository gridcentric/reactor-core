import pytest

from reactor.zookeeper.objects import RawObject
from reactor.objects.root import Reactor
from reactor.objects.manager import Managers
from reactor.objects.endpoint import Endpoints
from reactor.objects.ip_address import IPAddresses

def test_managers(reactor):
    assert isinstance(reactor.managers(), Managers)

def test_endpoints(reactor):
    assert isinstance(reactor.endpoints(), Endpoints)

def test_auth_hash(reactor):
    assert not reactor.auth_hash
    reactor.auth_hash = "test"
    assert reactor.auth_hash == "test"

def test_url(reactor):
    assert not reactor.url().get()
    pytest.raises(NotImplementedError, reactor.url().set, "test")
    assert not reactor.url().get()
    reactor.url().set("http://foo")
    assert reactor.url().get() == "http://foo"

def test_endpoint_ips(reactor):
    assert isinstance(reactor.endpoint_ips(), IPAddresses)

def test_new_ips(reactor):
    assert isinstance(reactor.new_ips(), IPAddresses)

def test_drop_ips(reactor):
    assert isinstance(reactor.drop_ips(), IPAddresses)
