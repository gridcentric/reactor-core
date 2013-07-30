from reactor.zookeeper.objects import DatalessObject

from . ip_address import IPAddresses

class Loadbalancers(DatalessObject):

    def locks(self, name):
        return self._get_child(name, clazz=IPAddresses)
