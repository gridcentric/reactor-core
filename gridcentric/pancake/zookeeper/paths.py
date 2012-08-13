"""
This defines the various paths used in zookeeper
"""

# The root path that all other paths hang off from.
ROOT = "/gridcentric/pancake"

# The path to the authorization hash used by the API to validate requests.
AUTH_HASH = "%s/auth" % (ROOT)
def auth_hash():
    return AUTH_HASH

# The path to the global domain.
DOMAIN = "%s/domain" % (ROOT)
def domain():
    return DOMAIN

# The global configuration.
CONFIG = "%s/config" % (ROOT)
def config():
    return CONFIG

# The subtree for managers.
MANAGERS = "%s/managers" % (ROOT)

# All available manager ips.
MANAGER_IPS = "%s/ips" % (MANAGERS)
def manager_ips():
    return MANAGER_IPS

# The IP node for a particular manager.
def manager_ip(ip):
    return "%s/%s" % (MANAGER_IPS, ip)

# All available manager configurations.
MANAGER_CONFIGS = "%s/configs" % (MANAGERS)
def manager_configs():
    return MANAGER_CONFIGS

# The node for a particular manager.
def manager_config(ip):
    return "%s/%s" % (MANAGER_CONFIGS, ip)

# All available manager keys / metrics.
MANAGER_KEYS = "%s/keys" % (MANAGERS)
MANAGER_METRICS = "%s/metrics" % (MANAGERS)
def managers():
    return MANAGER_KEYS

# The keys for a particular manager.
def manager_keys(name):
    return "%s/%s" % (MANAGER_KEYS, name)

# The metrics for a particular manager.
def manager_metrics(name):
    return "%s/%s" % (MANAGER_METRICS, name)

# The mappings of endpoint to ip address that have no connections
def manager_active_connections(name):
    return "%s/active_connections/%s" % (MANAGERS, name)

# The endpoints subtree. Basically anything related to a particular endpoint
# should be rooted here.
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
# ip is confirmed once it sends a message to a pancake.
def confirmed_ips(name):
    return "%s/confirmed_ip" % (endpoint(name))

# A particular ip that has been confirmed for the endpoint.
def confirmed_ip(name, ip_address):
    return "%s/%s" % (confirmed_ips(name), ip_address)

# The instance ids that have been marked as having an issue relating to them.
# Usually this issue will be related to connectivity issue.
def marked_instances(name):
    return "%s/marked_ip" % (endpoint(name))

# The particular instance id that has been marked for the endpoint. This is a
# running counter and once it has reached some configurable value the system
# should attempt to clean it up because there is something wrong with it.
def marked_instance(name, instance_id):
    return "%s/%s" % (marked_instances(name), instance_id)

# The instance ids that have been decommissioned. A decommissioned instance
# is basically marked for deletion but waiting for client / connections to
# finish up.
def decommissioned_instances(name):
    return "%s/decommissioned" % (endpoint(name))

# The particular instance id that has been decommissioned for a endpoint.
def decommissioned_instance(name, instance_id):
    return "%s/%s" % (decommissioned_instances(name), instance_id)

# New IPs currently not associated with any endpoint are logged here.
NEW_IPS = "%s/new_ips" % (ROOT)
def new_ips():
    return NEW_IPS

# A particular new ip.
def new_ip(ip_address):
    return "%s/%s" % (NEW_IPS, ip_address)

# IPs that are to be explicitly dropped.
DROP_IPS = "%s/drop_ips" % (ROOT)
def drop_ips():
    return DROP_IPS

# A particular IP to be dropped.
def drop_ip(ip_address):
    return "%s/%s" % (DROP_IPS, ip_address)

# Mapping of IP addresses to endpoints.
IP_ADDRESSES = "%s/ip_addresses" % (ROOT)
def ip_addresses():
    return IP_ADDRESSES

# Mapping for a particular IP.
def ip_address(ip):
    return "%s/%s" % (ip_addresses(), ip)
