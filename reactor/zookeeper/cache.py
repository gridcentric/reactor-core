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

from reactor import utils
from reactor.atomic import Atomic

from . objects import Collection

class Cache(Atomic):

    def __init__(self, zkobj, populate=None, update=None):
        super(Cache, self).__init__()
        self.zkobj = zkobj
        self._index = []
        self._cache = {}

        # Save the hooks for this cache.
        # We allow users to specify a populate hook, which
        # will be used to populate the cache when we see a
        # new entry, and an update hook, which will be called
        # whenever the collection of associated resources
        # changes.
        if populate is None:
            self._populate = self._default_populate
        else:
            self._populate = utils.callback(populate)
        if update is None:
            self._update_hook = self._default_update_hook
        else:
            self._update_hook = utils.callback(update)

        # NOTE: We require that this object is a zookeeper
        # collection object. Past this point, it's safe to
        # copy the add(), remove() methods to ourselves.
        assert isinstance(zkobj, Collection)
        self.add = zkobj.add
        self.remove = zkobj.remove
        self.as_map = zkobj.as_map
        self._get_child = zkobj._get_child

        # Start the watch.
        self._update(zkobj._list_children(watch=self.update))

    @Atomic.sync
    def _get_cache(self, name):
        # NOTE: This doesn't check for membership
        # in the cache, rather it checks if it is
        # non-None. This is because we don't accept
        # False / None as a true cache value and we
        # want to call populate() when it appears.
        if not self._cache.get(name):
            raise KeyError(name)
        return self._cache.get(name)

    @Atomic.sync
    def _set_cache(self, name, value):
        if self._cache.get(name):
            return self._cache.get(name)
        else:
            self._cache[name] = value
            return value

    def get(self, name, **kwargs):
        try:
            value = self._get_cache(name)
        except KeyError:
            value = self._populate(name, **kwargs)
        return self._set_cache(name, value)

    def _default_populate(self, name, **kwargs):
        # The default implementation here is to
        # simply fetch the associated value in the
        # zkobj. This is fine, it can be overriden
        # by subclasses.
        return self.zkobj.get(name)

    @Atomic.sync
    def _update(self, values):
        values.sort()
        to_remove = []
        for value in self._cache:
            if not value in values:
                to_remove.append(value)
        for value in to_remove:
            del self._cache[value]
        if self._index != values:
            self._index = values
            return True
        else:
            return False

    def update(self, values):
        if self._update(values):
            self._update_hook()

    def _default_update_hook(self):
        pass

    @Atomic.sync
    def list(self):
        return self._index

    def __repr__(self):
        return "cache[%s]" % self.zkobj._path
