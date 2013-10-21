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
import subprocess

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

def find_default():
    # Query all routes.
    ip_route = subprocess.Popen(
        ["ip", "route"],
        stdout=subprocess.PIPE,
        close_fds=True)
    (stdout, _) = ip_route.communicate()
    if ip_route.returncode != 0:
        return find_global()[0]

    # Find the default gw.
    for line in stdout:
        fields = line.strip().split()
        if len(fields) > 2 and \
           fields[0] == "default" and \
           fields[1] == "via":
            gateway_ip = fields[2]

            # Get the local route for the default gw.
            this_ip_route = subprocess.Popen(
                ["ip", "route", "get", gateway_ip],
                stdout=subprocess.PIPE,
                close_fds=True)
            (this_stdout, _) = this_ip_route.communicate()

            for line in this_stdout:
                fields = line.strip().split()
                if len(fields) >= 7 and \
                   fields[5] == "src":
                    return fields[6]

    return find_global()[0]
