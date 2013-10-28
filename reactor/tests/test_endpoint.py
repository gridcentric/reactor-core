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

import uuid

from reactor.endpoint import State

def test_key(endpoint):
    assert endpoint.key()
    endpoint.config.url = "http://url1"
    key1 = endpoint.key()
    assert key1
    assert key1 != "http://url1"
    endpoint.config.url = "http://url2"
    key2 = endpoint.key()
    assert key2
    assert key1 != key2
    endpoint.config.url = "http://url1"
    key3 = endpoint.key()
    assert key3
    assert key1 == key3

def test_managed(reactor, endpoint):
    def _assert_manager(is_value):
        managers = map(
            lambda x: reactor.endpoints().get(x).manager,
            reactor.endpoints().list())
        assert managers == [ is_value ] * len(managers)

    _assert_manager(None)
    test_uuid = str(uuid.uuid4())
    endpoint.managed(test_uuid)
    _assert_manager(test_uuid)

def test_update(endpoint):
    pass

def test_session_opened(endpoint):
    pass

def test_session_closed(endpoint):
    pass

def test_drop_sessions(endpoint):
    pass

def test_update_state(endpoint):
    pass

def test_update_config(endpoint):
    pass

def test_update_confirmed(endpoint):
    pass

def test_update_decommissioned_instances(endpoint):
    pass

def test_ip_confirmed(endpoint):
    pass

def test_ip_dropped(endpoint):
    pass

def test_ips(endpoint):
    pass

def test_backends(endpoint):
    pass

def test_reload(endpoint):
    pass
