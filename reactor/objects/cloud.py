from reactor.zookeeper.objects import DatalessObject

class Clouds(DatalessObject):

    def tree(self, name):
        return self._get_child(name, clazz=DatalessObject)
