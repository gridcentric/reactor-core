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

def test_get_connection_disconnected(zk_client):
    assert not zk_client.connected()
    assert zk_client.get_connection() != None

def test_get_connected_connected(zk_client):
    assert not zk_client.connected()
    zk_client.connect()
    orig_zk_conn = zk_client._zk_conn
    assert zk_client.get_connection() == orig_zk_conn
