from . import ROOT

# Manager information.
MANAGERS = "%s/managers" % (ROOT)

def manager_ips():
    return "%s/ips" % MANAGERS

# The IP node for a particular manager.
def manager_ip(ip):
    return "%s/%s" % (manager_ips(), ip)

# All available manager configurations.
def manager_configs():
    return "%s/configs" % (MANAGERS)

# The node for a particular manager.
def manager_config(ip):
    return "%s/%s" % (manager_configs(), ip)

# All available managers.
def managers():
    return "%s/keys" % (MANAGERS)

# The keys for a particular manager.
def manager_keys(name):
    return "%s/keys/%s" % (MANAGERS, name)

# The logs for a given manager.
def manager_log(name):
    return "%s/log/%s" % (MANAGERS, name)

# The metrics for a particular manager.
def manager_metrics(name):
    return "%s/metrics/%s" % (MANAGERS, name)

# The mappings of endpoint to ip address that have no connections
def manager_active_connections(name):
    return "%s/active_connections/%s" % (MANAGERS, name)
