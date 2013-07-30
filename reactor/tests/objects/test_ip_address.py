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
