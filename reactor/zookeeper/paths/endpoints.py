from . import ROOT

# Endpoint information.
ENDPOINTS = "%s/endpoint" % (ROOT)

def endpoints():
    return ENDPOINTS

# The subtree for a particular endpoint.
def endpoint(name):
    return "%s/%s" % (ENDPOINTS, name)

# The action for an endpoint.
def endpoint_state(name):
    return "%s/state" % (endpoint(name))

# The manager for this endpoint.
def endpoint_manager(name):
    return "%s/manager" % (endpoint(name))

# Binary log data for this endpoint.
def endpoint_log(name):
    return "%s/log" % (endpoint(name))

# The custom metrics for a particular host.
def endpoint_ip_metrics(name, ip_address):
    return "%s/ip_metrics/%s" % (endpoint(name), ip_address)

# The global custom metrics for a endpoint (posted by the API).
def endpoint_custom_metrics(name):
    return "%s/custom_metrics" % (endpoint(name))

# The updated metrics for a particular endpoint (posted by the manager).
def endpoint_live_metrics(name):
    return "%s/live_metrics" % (endpoint(name))

# The updated connections for a particular endpoint (posted by the manager).
def endpoint_live_active(name):
    return "%s/live_active" % (endpoint(name))

# The ips that have been confirmed by the system for a particular endpoint. An
# ip is confirmed once it sends a message to a reactor.
def endpoint_confirmed_ips(name):
    return "%s/confirmed_ips" % (endpoint(name))

# A particular ip that has been confirmed for the endpoint.
def endpoint_confirmed_ip(name, ip_address):
    return "%s/%s" % (endpoint_confirmed_ips(name), ip_address)
