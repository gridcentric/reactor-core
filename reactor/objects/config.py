import json

from reactor.zookeeper.objects import RawObject
from reactor.config import fromstr

class ConfigObject(RawObject):

    # NOTE: For endpoints & managers, they store the basic configuration value
    # as their contents. Because we still support endpoints that have ini-style
    # configurations, we override our deserialize to be a little bit smarter
    # than the average bear.

    def _deserialize(self, value):
        return fromstr(value)

    def _serialize(self, value):
        if type(value) == str or type(value) == unicode:
            return value
        else:
            return json.dumps(value)
