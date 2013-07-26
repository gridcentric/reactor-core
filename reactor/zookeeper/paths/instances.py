from . endpoints import endpoint

def endpoint_instances(name):
    return "%s/instances" % (endpoint(name))

def endpoint_instance(name, instance_id):
    return "%s/%s" % (endpoint_instances(name), instance_id)

# The instance ids that have been marked as having an issue relating to them.
# Usually this issue will be related to connectivity issue.
def endpoint_marked_instances(name):
    return "%s/marked_ip" % (endpoint(name))

# The particular instance id that has been marked for the endpoint. This is a
# running counter and once it has reached some configurable value the system
# should attempt to clean it up because there is something wrong with it.
def endpoint_marked_instance(name, instance_id):
    return "%s/%s" % (endpoint_marked_instances(name), instance_id)

# The instance ids that have been decommissioned. A decommissioned instance
# is basically marked for deletion but waiting for client / connections to
# finish up.
def endpoint_decommissioned_instances(name):
    return "%s/decommissioned" % (endpoint(name))

# The particular instance id that has been decommissioned for a endpoint.
def endpoint_decommissioned_instance(name, instance_id):
    return "%s/%s" % (endpoint_decommissioned_instances(name), instance_id)
