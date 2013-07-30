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
