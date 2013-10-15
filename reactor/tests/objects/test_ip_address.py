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

from reactor.tests.pytest_plugin import fixture, zk_client

@fixture()
def ips(request):
    from reactor.objects.ip_address import IPAddresses
    return IPAddresses(zk_client(request))

def test_add(ips):
    assert len(ips.list()) == 0
    ips.add("ip1")
    assert len(ips.list()) == 1

def test_remove(ips):
    ips.add("ip1")
    ips.add("ip2")
    assert len(ips.list()) == 2
    ips.remove("ip1")
    assert ips.list() == ["ip2"]

def test_data(ips):
    ips.add("ip1", value="foo")
    assert ips.get("ip1") == "foo"

def test_as_map(ips):
    ips.add("ip1", value="foo")
    ips.add("ip2", value="bar")
    assert ips.as_map() == {"ip1" : "foo", "ip2" : "bar"}

def test_lock(ips):
    ips.add("ip1", value="foo")
    ips.add("ip3", value="bar")
    assert ips.lock(["ip1", "ip2", "ip3"], value="held") == "ip2"
    assert ips.get("ip2") == "held"

def test_find(ips):
    ips.add("ip1", value="foo")
    ips.add("ip2", value="bar")
    assert ips.find("bar") == ["ip2"]
