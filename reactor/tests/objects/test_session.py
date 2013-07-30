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
