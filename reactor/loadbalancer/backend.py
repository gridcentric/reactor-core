"""
Interface to backend instances.
"""

class Backend(object):

    def __init__(self, ip, port=0, weight=1):
        self._ip = ip
        self._port = port
        self._weight = weight

    @property
    def ip(self):
        return self._ip

    @property
    def port(self):
        return self._port

    @property
    def weight(self):
        return self._weight
