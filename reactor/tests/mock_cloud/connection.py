from uuid import uuid4
from struct import pack, unpack
from socket import inet_ntoa, inet_aton
from collections import namedtuple

from reactor.cloud.connection import CloudConnection

MockInstance = namedtuple('MockInstance', ['id', 'name', 'addresses', 'params', 'sequence'])

def instance_sequencer():
    current = 0
    while True:
        current += 1
        yield current

def ip_to_int(ip):
    return unpack("!I", inet_aton(ip))[0]

def int_to_ip(ip_int):
    return inet_ntoa(pack("!I", ip_int))

def ip_range_generator(base, count):
    base_ip = ip_to_int(base)
    max_ip = base_ip + count
    current = base_ip
    while current < max_ip:
        yield int_to_ip(current)
        current += 1

class Connection(CloudConnection):

    """ Mock cloud connection. """

    def __init__(self, *args, **kwargs):
        CloudConnection.__init__(self, *args, **kwargs)
        self.instances = {} # map(instance.id => MockInstance)
        self.ip_generator = ip_range_generator('172.16.0.1', 255)

    def id(self, config, instance):
        return instance.id

    def name(self, config, instance):
        return instance.name

    def description(self):
        return "Mock Cloud Connection"

    def addresses(self, config, instance):
        return instance.addresses

    def list_instances(self, config):
        return sorted(self.instances.values(), key=lambda x: x.sequence)

    def start_instance(self, config, params={}, ip=None, instance_id=None, name=None):
        generated_id = str(uuid4())
        instance = MockInstance(
            sequence = instance_sequencer(),
            name = name or generated_id,
            id = instance_id or generated_id,
            addresses = [ip or self.ip_generator.next()],
            params = params)

        self.instances[instance.id] = instance
        return instance

    def delete_instance(self, config, instance_id):
        # Tests should never delete instances that have not been created.
        del self.instances[instance_id]
