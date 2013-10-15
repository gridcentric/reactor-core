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
def sessions(request):
    from reactor.objects.session import Sessions
    return Sessions(zk_client(request))

def test_drop(sessions):
    sessions.drop("client1")
    assert sessions.drop_map() == {}
    sessions.opened("client1", "backend1")
    sessions.drop("client1")
    assert sessions.drop_map() == {"client1": "backend1"}
    sessions.closed("client1")
    assert sessions.drop_map() == {"client1": "backend1"}
    sessions.dropped("client1")
    assert sessions.drop_map() == {}

def test_basic(sessions):
    sessions.opened("client1", "backend1")
    sessions.opened("client2", "backend2")
    sessions.closed("client1")
    assert sessions.active() == ["client2"]
    assert sessions.backend("client2") == "backend2"
