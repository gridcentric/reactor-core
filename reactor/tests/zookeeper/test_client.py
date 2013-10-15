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

def test_connect_no_servers(zk_client):
    assert not zk_client.connected()
    zk_client.connect()
    assert zk_client.connected()

def test_connect_already_connected(zk_client):
    assert not zk_client.connected()
    zk_client.connect()
    assert zk_client.connected()
    zk_client.connect()
    assert zk_client.connected()

def test_connect_new_servers(zk_client):
    assert not zk_client.connected()
    zk_client.connect()
    assert zk_client.connected()
    orig_servers = zk_client._zk_servers
    new_servers = ["newserver1", "newserver2"]
    zk_client.connect(new_servers)
    assert zk_client.connected()
    assert zk_client._zk_servers == new_servers

def test_disconnect(zk_client):
    assert not zk_client.connected()
    zk_client.connect()
    assert zk_client.connected()
    zk_client.disconnect()
    assert not zk_client.connected()

def test_connect_disconnected(zk_client):
    assert not zk_client.connected()
    assert zk_client.connect() != None

def test_connect_connected(zk_client):
    assert not zk_client.connected()
    zk_client.connect()
    orig_zk_conn = zk_client._zk_conn
    assert zk_client.connect() == orig_zk_conn
