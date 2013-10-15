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

import os
import json
import binascii
import array
import threading
import random

class ZookeeperObject(object):

    """ An object abstraction around the Zookeeper client interface. """

    def __init__(self, zk_client, path='/'):
        super(ZookeeperObject, self).__init__()
        self._zk_client = zk_client
        self._content_watches = {}
        self._child_watches = {}
        self._path = path
        self._watch_content = None
        self._watch_children = None
        self._lock = threading.RLock()

    def __del__(self):
        self.unwatch()

    def unwatch(self):
        client = self._zk_client.connect()
        with self._lock:
            if self._watch_content:
                client.clear_watch_fn(self._watch_content)
                self._watch_content = None
            if self._watch_children:
                client.clear_watch_fn(self._watch_children)
                self._watch_children = None

    def _cast_as(self, clazz):
        return clazz(self._zk_client, self._path)

    def _serialize(self, data):
        raise NotImplementedError()

    def _deserialize(self, data):
        raise NotImplementedError()

    def _get_data(self, watch=None):
        client = self._zk_client.connect()
        if watch:
            with self._lock:
                if self._watch_content:
                    client.clear_watch_fn(self._watch_content)
                self._watch_content = lambda x: watch(self._deserialize(x))
                return self._deserialize(
                    client.watch_contents(self._path, self._watch_content))
        else:
            return self._deserialize(client.read(self._path))

    def _set_data(self, value="", **kwargs):
        return self._zk_client.connect().write(
            self._path, self._serialize(value), **kwargs)

    def _list_children(self, watch=None):
        client = self._zk_client.connect()
        if watch:
            with self._lock:
                if self._watch_children:
                    client.clear_watch_fn(self._watch_children)
                self._watch_children = lambda x: watch(x or [])
                return client.watch_children(self._path, self._watch_children) or []
        else:
            return client.list_children(self._path) or []

    def _get_child(self, child, clazz=None):
        if clazz is None:
            return self.__class__(self._zk_client, os.path.join(self._path, child))
        else:
            return clazz(self._zk_client, os.path.join(self._path, child))

    def _delete(self):
        client = self._zk_client.connect()
        with self._lock:
            if self._watch_content:
                client.clear_watch_fn(self._watch_content)
            if self._watch_children:
                client.clear_watch_fn(self._watch_children)
        client.delete(self._path)

class DatalessObject(ZookeeperObject):

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

class Collection(DatalessObject):

    def get(self, name):
        return self._get_child(name, clazz=JSONObject)._get_data()

    def list(self, **kwargs):
        return self._list_children(**kwargs)

    def add(self, name, value=None, **kwargs):
        return self._get_child(name, clazz=JSONObject)._set_data(value, **kwargs)

    def remove(self, name):
        self._get_child(name)._delete()

    def clear(self):
        self._delete()

    def as_map(self):
        return dict(map(lambda x: (x, self.get(x)), self.list()))

    def lock(self, items, value=None):
        locked = self.list()
        # NOTE: We shuffle the list of available items, for two
        # reasons. First, to avoid obviously colliding with other
        # threads / managers that are trying to grab an item.
        # Second, if a VM is broken we can end up with the same
        # one over and over again. This is less than ideal and
        # it's better to have a random assignment.
        candidates = [item for item in items if not item in locked]
        random.shuffle(candidates)
        for item in candidates:
            # Try to lock each of the given candidates sequentially.
            if self._get_child(item, clazz=JSONObject)._set_data(
                value, ephemeral=True, exclusive=True):
                return item
        return None

    def find(self, value):
        locked = self.as_map()
        return [item for (item, item_value) in locked.items() if value == item_value]

def attr(name, **kwargs):
    clazz = kwargs.pop("clazz", None)
    def getx(self):
        return self._get_child(name, clazz=clazz)._get_data()
    def setx(self, value):
        return self._get_child(name, clazz=clazz)._set_data(value, **kwargs)
    def delx(self):
        raise NotImplementedError()
    return property(getx, setx, delx)
