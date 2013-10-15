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

from reactor.zookeeper.objects import DatalessObject
from reactor.zookeeper.objects import RawObject

# Currently active sessions.
ACTIVE = "active"

# Sessions that should be dropped.
DROP = "drop"

class Sessions(DatalessObject):

    def active(self):
        return self._get_child(ACTIVE)._list_children()

    def backend(self, client):
        return self._get_child(ACTIVE)._get_child(client, clazz=RawObject)._get_data()

    def opened(self, client, backend):
        self._get_child(ACTIVE)._get_child(
            client, clazz=RawObject)._set_data(backend, ephemeral=True)

    def closed(self, client):
        self._get_child(ACTIVE)._get_child(client)._delete()

    def dropped(self, client):
        self._get_child(DROP)._get_child(client)._delete()

    def drop(self, client):
        backend = self.backend(client)
        if backend:
            self._get_child(DROP)._get_child(client, clazz=RawObject)._set_data(backend)

    def drop_map(self):
        return dict(map(
            lambda x: (x, self._get_child(DROP)._get_child(
                x, clazz=RawObject)._get_data()),
            self._get_child(DROP)._list_children()))

    def active_map(self):
        return dict(map(
            lambda x: (x, self._get_child(ACTIVE)._get_child(
                x, clazz=RawObject)._get_data()),
            self._get_child(ACTIVE)._list_children()))
