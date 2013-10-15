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
def instances(request):
    from reactor.objects.instance import Instances
    return Instances(zk_client(request))

def test_add(instances):
    assert len(instances._list_children()) == 0
    instances.add("foo1")
    assert instances._list_children() == ["foo1"]

def test_remove(instances):
    instances.add("foo1")
    instances.add("foo2")
    assert len(instances._list_children()) == 2
    instances.remove("foo1")
    assert instances._list_children() == ["foo2"]

def test_data(instances):
    instances.add("foo1", "mydata1")
    instances.add("foo2", "mydata2")
    assert instances.get("foo1") == "mydata1"
    assert instances.get("foo2") == "mydata2"

def test_as_map(instances):
    instances.add("foo1", "mydata1")
    instances.add("foo2", "mydata2")
    assert instances.as_map() == {"foo1" : "mydata1", "foo2" : "mydata2"}
