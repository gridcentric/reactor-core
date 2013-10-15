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

import re
import time

from reactor.zookeeper.objects import JSONObject
from reactor.zookeeper.objects import Collection

class Ring(Collection):

    def __init__(self, *args, **kwargs):
        super(Ring, self).__init__(*args, **kwargs)
        self._entries = None

    @staticmethod
    def _get_ts_tuple(name):
        m = re.match("(\d+)_-?(\d*)$", name)
        if m:
            # Return the timestamp, followed by id.
            return (int(m.group(1)), int(m.group(2)), name)
        else:
            # Return no logical ordering.
            # NOTE: These nodes won't generally be
            # fetched below in entries(), and they will
            # be cleaned out by the system first.
            return (0, 0, name)

    @staticmethod
    def _sort_children(children):
        return sorted(children, key=Ring._get_ts_tuple)

    def _get_entries(self):
        with self._lock:
            if self._entries is None:
                self._entries = Ring._sort_children(self._list_children())
            return self._entries

    def add(self, data, limit=None):
        # Create a named (sortable above).
        name = str(int(time.time())) + "_"

        # Write out a new entry to Zookeeper (sequentialy).
        entry = self._get_child(
            name, clazz=JSONObject)._set_data(data, sequential=True)

        # Add it to our list of entries.
        with self._lock:
            self._get_entries().append(entry)

        # Remove old zookeeper nodes.
        to_remove = []
        with self._lock:
            # Prune down to the limit.
            # NOTE: It's possible that someone else
            # is logging here simultaneously, but we
            # only delete entries that we've added.
            # (Or that were there when this object
            # was originally created!).
            if limit is not None:
                limit = int(limit)
                assert limit >= 0
                while len(self._get_entries()) > limit:
                    to_remove.append(self._get_entries().pop(0))
        for name in to_remove:
            self._get_child(name)._delete()

    def entries(self, since=None, limit=None):
        # This will asynchrously read all entries from zookeeper
        # directly. We're not really worried about race conditions
        # here, as this ring is only used by the log currently.
        timestamps = sorted(map(Ring._get_ts_tuple, self._list_children()))
        if since is not None:
            timestamps = [ts for ts in timestamps if ts[0] > since]
        values = map(lambda x: self._get_child(
            x, clazz=JSONObject)._get_data(),
            map(lambda x: x[2], timestamps))
        return [value for value in values if value is not None][:limit]
