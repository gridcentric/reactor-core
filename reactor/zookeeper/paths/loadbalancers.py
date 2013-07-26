from . import ROOT

# The loadbalancer subtree.
LOADBALANCERS = "%s/loadbalancers" % (ROOT)

def loadbalancer_ips(name):
    return "%s/%s" % (LOADBALANCERS, name)

# Metadata for a particular IP.
def loadbalancer_ip(name, ip):
    return "%s/%s" % (loadbalancer_ips(name), ip)
