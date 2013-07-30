"""
Interface to cloud instances.
"""

class Instance(object):

    def __init__(self, id, name, ips):
        self._id = str(id)
        self._name = name
        self._ips = ips

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @property
    def ips(self):
        return self._ips
