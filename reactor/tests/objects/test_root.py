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
