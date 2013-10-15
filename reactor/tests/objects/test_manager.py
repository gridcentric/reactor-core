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
def managers(request):
    from reactor.objects.manager import Managers
    return Managers(zk_client(request))

def test_active(managers):
    assert len(managers.key_map()) == 0
    assert len(managers.info_map()) == 0

def test_register(managers):
    managers.set_config("test", "thisisaconfig")
    assert len(managers.key_map()) == 0
    assert len(managers.list()) == 1
    managers.register(ips=["myip"], uuid="myuuid", info=["key1", "key2"])
    assert len(managers.list()) == 1
    assert len(managers.key_map()) == 1

def test_info(managers):
    managers.register(ips=["myip"], uuid="myuuid", info=["key1", "key2"])
    assert not "notmyuuid" in managers.info_map()
    assert managers.info_map()["myuuid"] == ["key1", "key2"]
    assert len(managers.info_map()) == 1
