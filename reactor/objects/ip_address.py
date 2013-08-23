import random

from reactor.zookeeper.objects import JSONObject
from reactor.zookeeper.objects import Collection

class IPAddresses(Collection):

    def lock(self, ips, value=None):
        locked = self.list()
        # NOTE: We shuffle the list of available IPs, for two
        # reasons. First, to avoid obviously colliding with other
        # threads / managers that are trying to grab an IP.
        # Second, if a VM is broken we can end up with the same
        # one over and over again. This is less than ideal and 
        # it's better to have a random assignment.
        candidates = [ip for ip in ips if not ip in locked]
        random.shuffle(candidates)
        for ip in candidates:
            # Try to lock each of the given candidates sequentially.
            if self._get_child(ip, clazz=JSONObject)._set_data(
                value, ephemeral=True, exclusive=True):
                return ip
        return None

    def find(self, value):
        locked = self.as_map()
        return [ip for (ip, ip_value) in locked.items() if value == ip_value]
