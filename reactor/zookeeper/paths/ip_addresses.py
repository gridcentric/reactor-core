from . import ROOT

# New IPs currently not associated with any endpoint are logged here.
NEW_IPS = "%s/new_ips" % (ROOT)
DROP_IPS = "%s/drop_ips" % (ROOT)

def new_ips():
    return NEW_IPS

def drop_ips():
    return DROP_IPS

# A particular new ip.
def new_ip(ip_address):
    return "%s/%s" % (NEW_IPS, ip_address)

# A particular IP to be dropped.
def drop_ip(ip_address):
    return "%s/%s" % (DROP_IPS, ip_address)

# IP Address mappings.
IP_ADDRESSES = "%s/ip_addresses" % (ROOT)

def ip_addresses():
    return IP_ADDRESSES

# Mapping for a particular IP.
def ip_address(ip):
    return "%s/%s" % (ip_addresses(), ip)
