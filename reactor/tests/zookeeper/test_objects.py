import array

from reactor.zookeeper.objects import ZookeeperObject, JSONObject, RawObject, BinObject

def _test_obj(obj):
    if isinstance(obj, JSONObject):
        return { "a" : { "b" : [ "c", "d", "e" ] } }
    elif isinstance(obj, RawObject):
        return "foo"
    elif isinstance(obj, BinObject):
        return array.array("b", [1, 1, 2, 3, 5, 8])
    else:
        raise NotImplementedError()

def test_create(zk_conn, zk_object):
    assert not zk_conn.exists(zk_object._path)
    zk_object.save()

def test_save_contents(zk_object):
    test_obj = _test_obj(zk_object)
    zk_object.save(test_obj)
    assert zk_object.load() == test_obj

def test_watch_contents(zk_conn, zk_object):
    test_obj = _test_obj(zk_object)
    watch_ref = [False]
    def watch_fired(value):
        watch_ref[0] = value
    assert not zk_object.load(watch=watch_fired)
    zk_object.save(test_obj)
    zk_conn.sync()
    assert watch_ref[0] == test_obj
    zk_object.save(None)
    zk_conn.sync()
    assert watch_ref[0] != test_obj

def test_watch_removed(zk_conn, zk_object):
    test_obj = _test_obj(zk_object)
    watch_ref = [False]
    def watch_fired(value):
        watch_ref[0] = value
    assert not zk_object.load(watch=watch_fired)
    zk_object.unwatch()
    zk_object.save(test_obj)
    zk_conn.sync()
    assert watch_ref[0] == False

def test_list(zk_object):
    assert zk_object.list() == []
    child = zk_object.get("child")
    child.save()
    assert zk_object.list() == ["child"]
    child.delete()
    assert zk_object.list() == []

def test_watch_children(zk_conn, zk_object):
    watch_ref = [False]
    def watch_fired(value):
        watch_ref[0] = value
    assert zk_object.list(watch=watch_fired) == []
    child = zk_object.get("child")
    child.save()
    zk_conn.sync()
    assert watch_ref[0] == ["child"]

def test_watch_children(zk_conn, zk_object):
    watch_ref = [False]
    def watch_fired(value):
        watch_ref[0] = value
    assert zk_object.list(watch=watch_fired) == []
    zk_object.unwatch()
    child = zk_object.get("child")
    child.save()
    zk_conn.sync()
    assert watch_ref[0] == False

def test_delete(zk_conn, zk_object):
    assert not zk_conn.exists(zk_object._path)
    zk_object.save()
    assert zk_conn.exists(zk_object._path)
