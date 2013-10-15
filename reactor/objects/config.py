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

import json

from reactor.zookeeper.objects import RawObject
from reactor.config import fromstr

class ConfigObject(RawObject):

    # NOTE: For endpoints & managers, they store the basic configuration value
    # as their contents. Because we still support endpoints that have ini-style
    # configurations, we override our deserialize to be a little bit smarter
    # than the average bear.

    def _deserialize(self, value):
        return fromstr(value)

    def _serialize(self, value):
        if type(value) == str or type(value) == unicode:
            return value
        else:
            return json.dumps(value)
