from reactor.zookeeper.objects import DatalessObject
from reactor.zookeeper.objects import RawObject

# Currently active sessions.
ACTIVE = "active"

# Sessions that should be dropped.
DROP = "drop"

class Sessions(DatalessObject):

    def active(self):
        return self._get_child(ACTIVE)._list_children()

    def backend(self, client):
        return self._get_child(ACTIVE)._get_child(client, clazz=RawObject)._get_data()

    def opened(self, client, backend):
        self._get_child(ACTIVE)._get_child(
            client, clazz=RawObject)._set_data(backend, ephemeral=True)

    def closed(self, client):
        self._get_child(ACTIVE)._get_child(client)._delete()

    def dropped(self, client):
        self._get_child(DROP)._get_child(client)._delete()

    def drop(self, client):
        backend = self.backend(client)
        if backend:
            self._get_child(DROP)._get_child(client, clazz=RawObject)._set_data(backend)

    def drop_map(self):
        return dict(map(
            lambda x: (x, self._get_child(DROP)._get_child(
                x, clazz=RawObject)._get_data()),
            self._get_child(DROP)._list_children()))

    def active_map(self):
        return dict(map(
            lambda x: (x, self._get_child(ACTIVE)._get_child(
                x, clazz=RawObject)._get_data()),
            self._get_child(ACTIVE)._list_children()))
