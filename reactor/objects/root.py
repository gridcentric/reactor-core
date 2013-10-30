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

from reactor.zookeeper.objects import DatalessObject
from reactor.zookeeper.objects import JSONObject
from reactor.zookeeper.objects import RawObject
from reactor.zookeeper.objects import attr

from . import manager
from . import endpoint
from . import ip_address
from . import loadbalancer
from . import cloud

# The root path.
REACTOR = "/reactor"

# The path to the authorization hash used by the API to validate requests.
AUTH_HASH = "auth"

# The path to the reactor URL.
URL = "url"

# The path to the collection of managers.
MANAGERS = "managers"

# The path to the collection of endpoints.
ENDPOINTS = "endpoints"

# The path to endpoint mapping of IP addresses.
IP_ADDRESSES = "ip_addresses"

# Unregister IP addresses.
NEW_IPS = "new_ips"

# IP addresses that are to be dropped.
DROP_IPS = "drop_ips"

# Loadbalancer objects.
LOADBALANCERS = "loadbalancers"

# Cloud objects.
CLOUDS = "clouds"


class URLObject(RawObject):

    VALID_REGEX = "(http|https)://[a-zA-Z0-9]+[a-zA-Z0-9.]*(:[0-9]+|)(/.*|)"

    def get(self, watch=None):
        return self._get_data(watch=watch)

    def set(self, value):
        # Sanity check the value of the URL being set here.
        # Because it lead to all kinds of problems, this is
        # a very simple validation that will happen on the
        # set side (and throw an exception to whatever API
        # caller happens to originate this request).
        if not value:
            self._delete()
        elif not re.match(self.VALID_REGEX, value):
            raise NotImplementedError()
        else:
            return self._set_data(value)

class Reactor(DatalessObject):

    def __init__(self, client, path=REACTOR):
        super(Reactor, self).__init__(client, path=path)

    auth_hash = attr(AUTH_HASH, clazz=JSONObject)

    def url(self):
        return self._get_child(URL, clazz=URLObject)

    def managers(self):
        return self._get_child(MANAGERS, clazz=manager.Managers)

    def endpoints(self):
        return self._get_child(ENDPOINTS, clazz=endpoint.Endpoints)

    def clouds(self):
        return self._get_child(CLOUDS, clazz=cloud.Clouds)

    def loadbalancers(self):
        return self._get_child(LOADBALANCERS, clazz=loadbalancer.Loadbalancers)

    def endpoint_ips(self):
        return self._get_child(IP_ADDRESSES, clazz=ip_address.IPAddresses)

    def drop_ips(self):
        return self._get_child(DROP_IPS, clazz=ip_address.IPAddresses)

    def new_ips(self):
        return self._get_child(NEW_IPS, clazz=ip_address.IPAddresses)

    def dump(self):
        self._dump(clazz=RawObject)
