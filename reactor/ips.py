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

import socket

def list_local_ips():
    from netifaces import interfaces, ifaddresses, AF_INET
    ip_list = []
    for interface in interfaces():
        addresses = ifaddresses(interface)
        if AF_INET in addresses:
            for link in addresses[AF_INET]:
                ip_list.append(link['addr'])
    return ip_list

def is_local(host):
    remote = socket.gethostbyname(host)
    return remote.startswith("127.") or (remote in list_local_ips())

def is_public(host):
    ip = socket.gethostbyname(host)
    if ip.startswith("127."):
        return False
    else:
        return True

def any_local(hosts):
    return (True in map(is_local, hosts))

def find_global():
    return [x for x in list_local_ips() if is_public(x)]
