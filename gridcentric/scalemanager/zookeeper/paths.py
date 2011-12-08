
"""
This defines the various paths used in zookeeper
"""

root = "/gridcentric/scalemanager"

config = "%s/config" %(root)

services = "%s/service" % (root)
def service(name):
    return "%s/%s" %(services, name)

def service_managed(name):
    return "%s/%s/managed" %(services, name)

new_ips = "%s/new-ips" % (root)
def new_ip(ip_address):
    return "%s/%s" %(new_ips, ip_address)

def confirmed_ips(name):
    return "%s/confirmed_ip" % (service(name))

def confirmed_ip(name, ip_address):
    return "%s/%s" %(confirmed_ips(name), ip_address)
