#!/usr/bin/env python

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
    if ip.startswith("10.") or \
       ip.startswith("172.") or \
       ip.startswith("192.168.") or \
       ip.startswith("127."):
        return False
    else:
        return True

def is_private(host):
    ip = socket.gethostbyname(host)
    if ip.startswith("10.") or \
       ip.startswith("172.") or \
       ip.startswith("192.168."):
        return True
    else:
        return False

def any_local(hosts):
    return (True in map(is_local, hosts))

def find_global():
    filtered = [x for x in list_local_ips() if is_public(x)]
    if len(filtered) == 0:
        filtered = [x for x in list_local_ips() if is_private(x)]
    if len(filtered) == 0:
        return None
    else:
        return filtered[0]
