
"""
This defines the various paths used in zookeeper
"""

# The root path that all other paths hang off from.
root = "/gridcentric/scalemanager"

# The path to the authorization hash used by the API to validate requests.
auth_hash = "%s/auth" % (root)

# The main system configuration for all of the scale managers.
config = "%s/config" %(root)

# The services subtree. Basically anything related to a particular
# service should be rooted here.
services = "%s/service" % (root)
# The subtree for a particular service.
def service(name):
    return "%s/%s" %(services, name)

# A leaf node to determine if the service is already being managed.
def service_managed(name):
    return "%s/%s/managed" %(services, name)

# The ips that have been confirmed by the system for a particular service. An ip is
# confirmed once it sends a message to a scalemanager.
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

# New IPs currently not associated with any service are logged here
new_ips = "%s/new-ips" % (root)

# A particular new ip
def new_ip(ip_address):
    return "%s/%s" %(new_ips, ip_address)

# The agents subtree that holds the collected stats from the different agents.
agents = "%s/agents" % (root)

def agent(agent_name):
    return "%s/%s" % (agents, agent_name)

def agent_stats(agent_name, identifier):
    return "%s/%s" %(agent(agent_name), identifier)
