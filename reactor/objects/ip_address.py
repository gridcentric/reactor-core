from reactor.zookeeper.objects import JSONObject
from reactor.zookeeper.objects import Collection

class IPAddresses(Collection):

    def lock(self, ips, value=None):
        locked = self.list()
        candidates = [ip for ip in ips if not ip in locked]
        for ip in candidates:
            # Try to lock each of the given candidates sequentially.
            if self._get_child(ip, clazz=JSONObject)._set_data(
                value, ephemeral=True, exclusive=True):
                return ip
        return None

    def find(self, value):
        locked = self.as_map()
        return [ip for (ip, ip_value) in locked.items() if value == ip_value]
