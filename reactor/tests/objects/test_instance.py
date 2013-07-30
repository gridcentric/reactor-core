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
