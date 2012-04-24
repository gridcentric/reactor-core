#!/usr/bin/env python

"""
This defines the various paths used in zookeeper
"""

# The root path that all other paths hang off from.
ROOT = "/gridcentric/pancake"

# The path to the authorization hash used by the API to validate requests.
AUTH_HASH = "%s/auth" % (ROOT)
def auth_hash():
    return AUTH_HASH

# The global configuration.
CONFIG = "%s/config" % (ROOT)
def config():
    return CONFIG

# The services subtree. Basically anything related to a particular
# service should be rooted here.
SERVICES = "%s/service" % (ROOT)
def services():
    return SERVICES

# The subtree for a particular service.
def service(name):
    return "%s/%s" %(SERVICES, name)

# The subtree for managers.
MANAGERS = "%s/managers" % (ROOT)

# All available manager ips.
MANAGER_IPS = "%s/ips" % (MANAGERS)
def manager_ips():
    return MANAGER_IPS

# The IP node for a particular manager.
def manager_ip(ip):
    return "%s/%s" %(MANAGER_IPS, ip)

# All available manager configurations.
MANAGER_CONFIGS = "%s/configs" % (MANAGERS)
def manager_configs():
    return MANAGER_CONFIGS

# The node for a particular manager.
def manager_config(ip):
    return "%s/%s" %(MANAGER_CONFIGS, ip)

# All available manager keys.
MANAGER_KEYS = "%s/keys" % (MANAGERS)
def managers():
    return MANAGER_KEYS

# The keys for a particular manager.
def manager_keys(name):
    return "%s/%s" %(MANAGER_KEYS, name)

# The ips that have been confirmed by the system for a particular service. An ip is
# confirmed once it sends a message to a pancake.
def confirmed_ips(name):
    return "%s/confirmed_ip" % (service(name))

# A particular ip that has been confirmed for the service.
def confirmed_ip(name, ip_address):
    return "%s/%s" %(confirmed_ips(name), ip_address)

# The instance ids that have been marked as having an issue relating to them. Usually this
# issue will be related to connectivity issue.
def marked_instances(name):
    return "%s/marked_ip" % (service(name))

# The particular instance id that has been marked for the service. This is a running counter
# and once it has reached some configurable value the system should attempt to clean it up because
# there is something wrong with it.
def marked_instance(name, instance_id):
    return "%s/%s" %(marked_instances(name), instance_id)

# New IPs currently not associated with any service are logged here.
NEW_IPS = "%s/new-ips" % (ROOT)
def new_ips():
    return NEW_IPS

# A particular new ip.
def new_ip(ip_address):
    return "%s/%s" %(NEW_IPS, ip_address)

IP_ADDRESSES="%s/ip_addreses" % (ROOT)
def ip_addresses():
    return IP_ADDRESSES

def ip_address(ip):
    return "%s/%s" % (ip_addresses(), ip)
