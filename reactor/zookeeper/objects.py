import os
import json
import binascii
import array
import threading

class ZookeeperObject(object):

    """ An object abstraction around the Zookeeper client interface. """

    def __init__(self, zk_client, path='/'):
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
        raise NotImplementedError()

    def _deserialize(self, data):
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
        return self._zk_client.get_connection().write(
            self._path, self._serialize(val), **kwargs)

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

    def get(self, child, clazz=None):
        if clazz is None:
            return self.__class__(self._zk_client, os.path.join(self._path, child))
        else:
            return clazz(self._zk_client, os.path.join(self._path, child))

    def do_attr(self, name, value=None, **kwargs):
        if value is None:
            return self.get(name, clazz=kwargs.pop("clazz", None)).load()
        else:
            self.get(name, clazz=kwargs.pop("clazz", None)).save(value, **kwargs)

    def delete(self):
        client = self._zk_client.get_connection()
        with self._lock:
            if self._watch_content:
                client.clear_watch_fn(self._watch_content)
            if self._watch_children:
                client.clear_watch_fn(self._watch_children)
        client.delete(self._path)

class NullObject(ZookeeperObject):

    def _serialize(self, data):
        assert False

    def _deserialize(self, data):
        assert False

class RawObject(ZookeeperObject):

    def _serialize(self, data):
        return str(data)

    def _deserialize(self, data):
        return data

class JSONObject(ZookeeperObject):

    def _serialize(self, data):
        return json.dumps(data)

    def _deserialize(self, data):
        if data:
            return json.loads(data)
        else:
            return data

class BinObject(ZookeeperObject):

    def _serialize(self, data):
        return binascii.hexlify(data or '')

    def _deserialize(self, data):
        if data:
            try:
                data = array.array('b', binascii.unhexlify(data))
            except ValueError:
                data = None
        return data

def attr(name, **kwargs):
    obj = kwargs.pop('obj', False)
    def getx(self):
        if obj:
            return self.get(name, **kwargs)
        else:
            return self.do_attr(name, **kwargs)
    def setx(self, value):
        return self.do_attr(name, value=value, **kwargs)
    def delx(self):
        raise NotImplementedError()
    return property(getx, setx, delx)

def raw_attr(name, **kwargs):
    return attr(name, clazz=RawObject, **kwargs)

def json_attr(name, **kwargs):
    return attr(name, clazz=JSONObject, **kwargs)

def bin_attr(name, **kwargs):
    return attr(name, clazz=BinObject, **kwargs)
