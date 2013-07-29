import os
import json
import binascii
import array
import threading

class ZookeeperObject(object):

    """ An object abstraction around the Zookeeper client interface. """

    def __init__(self, zk_client, path):
        self._zk_client = zk_client
        self._content_watches = {}
        self._child_watches = {}
        self._path = path
        self._watch_content = None
        self._watch_children = None
        self._lock = threading.Lock()

    def __del__(self):
        self.unwatch()

    def unwatch(self):
        client = self._zk_client.get_connection()
        with self._lock:
            if self._watch_content:
                client.clear_watch_fn(self._watch_content)
            if self._watch_children:
                client.clear_watch_fn(self._watch_children)

    def _serialize(self, data):
        return data

    def _deserialize(self, data):
        return data

    def _test_object(self):
        raise NotImplementedError()

    def load(self, watch=None):
        client = self._zk_client.get_connection()
        if watch:
            with self._lock:
                if self._watch_content:
                    client.clear_watch_fn(self._watch_content)
                self._watch_content = lambda x: watch(self._deserialize(x))
                return self._deserialize(
                    client.watch_contents(self._path, self._watch_content))
        else:
            return self._deserialize(client.read(self._path))

    def save(self, val="", **kwargs):
        self._zk_client.get_connection().write(self._path, self._serialize(val), **kwargs)

    def list(self, watch=None):
        client = self._zk_client.get_connection()
        if watch:
            with self._lock:
                if self._watch_children:
                    client.clear_watch_fn(self._watch_children)
                self._watch_children = lambda x: watch(x or [])
                return client.watch_children(self._path, self._watch_children) or []
        else:
            return client.list_children(self._path) or []

    def get(self, child):
        return self.__class__(self._zk_client, os.path.join(self._path, child))

    def delete(self):
        client = self._zk_client.get_connection()
        with self._lock:
            if self._watch_content:
                client.clear_watch_fn(self._watch_content)
            if self._watch_children:
                client.clear_watch_fn(self._watch_children)
        client.delete(self._path)

class RawObject(ZookeeperObject):

    def _serialize(self, data):
        return str(data)

    def _deserialize(self, data):
        return data

    def _test_object(self):
        return "foo"

class JSONObject(ZookeeperObject):

    def _serialize(self, data):
        return json.dumps(data)

    def _deserialize(self, data):
        if data:
            return json.loads(data)
        else:
            return data

    def _test_object(self):
        return { "a" : { "b" : [ "c", "d" ] } }

class BinObject(ZookeeperObject):

    def _serialize(self, data):
        return binascii.hexlify(data)

    def _deserialize(self, data):
        if data:
            try:
                data = array.array('b', binascii.unhexlify(data))
            except:
                data = None
        return data

    def _test_object(self):
        return array.array('b', [1, 1, 2, 3, 5, 8])

def Attr(name, **kwargs):
    def getx(self):
        return self.do_attr(name, **kwargs)
    def setx(self, value):
        return self.do_attr(name, value=value, **kwargs)
    def delx(self):
        raise NotImplementedError()
    return property(getx, setx, delx)

def RawAttr(name):
    return Attr(name, clazz=RawObject)

def JSONAttr(name):
    return Attr(name, clazz=JSONObject)

def BinAttr(name):
    return Attr(name, clazz=BinObject)
