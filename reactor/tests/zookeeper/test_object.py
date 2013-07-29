def test_create(zk_conn, zk_object):
    assert not zk_conn.exists(zk_object._path)
    zk_object.save()

def test_save_contents(zk_object):
    zk_object.save(zk_object._test_object())
    assert zk_object.load() == zk_object._test_object()

def test_watch_contents(zk_conn, zk_object):
    watch_ref = [False]
    def watch_fired(value):
        watch_ref[0] = value
    assert not zk_object.load(watch=watch_fired)
    zk_object.save(zk_object._test_object())
    zk_conn.sync()
    assert watch_ref[0] == zk_object._test_object()

def test_watch_removed(zk_conn, zk_object):
    watch_ref = [False]
    def watch_fired(value):
        watch_ref[0] = value
    assert not zk_object.load(watch=watch_fired)
    zk_object.unwatch()
    zk_object.save(zk_object._test_object())
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
