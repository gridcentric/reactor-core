import json

from ConfigParser import SafeConfigParser
from StringIO import StringIO

class Config(object):

    def __init__(self, section='', obj=None, values=None):
        self._avail = []
        self._section = section

        # The underlying object is the magic of the config.
        # It contains essentially a specification of all the available
        # (and set) configuration values.  You can get multiple "views"
        # into the same configuration by passing around the same underlying
        # config object (or an instance of the config class).
        # For example:
        #   x = Config(values={}) <-- An empty configuration.
        #   y = MyConfig(obj=x)   <-- Shares the same values.
        if obj is None:
            self._obj = {}
        elif hasattr(obj, '_obj'):
            self._obj = obj._obj
        else:
            self._obj = obj

        # Populate from the class.
        # This takes all class attribues that do not start with an
        # underscore (and are not in the special list below) and turns
        # them into attributes in _avail.  These attributes are used
        # in _validate() below.
        for k in dir(self):
            if k.startswith('_'):
                continue

            # Ensure it's not one of our types.
            if k in dir(Config):
                continue

            # Mark it in our list to be validated.
            self._avail.append(k)
            setattr(self, k, getattr(self, k))

        if values:
            self._update(values)

    def _update(self, obj):
        if type(obj) == str:
            try:
                obj = json.loads(obj)
            except:
                if len(obj) == 0:
                    obj = {}
                else:
                    config = SafeConfigParser()
                    config.readfp(StringIO(obj))
                    obj = fromini(config)

        for name,section in obj.items():
            for k,v in section.items():
                info = self._obj.get(name, {}).get(k, None)
                if info:
                    info["value"] = v

    def _spec(self):
        return self._obj

    def _values(self):
        rval = {}
        for name,section in self._obj.items():
            rval[name] = {}
            for k,v in section.items():
                if v.get("value") and v.get("default") != v.get("value"):
                    rval[name][k] = v.get("value")
        return rval

    def _validate(self):
        for k in self._avail:
            setattr(self, k, getattr(self, k))

    def _get(self, key, default):
        return self._obj.get(self._section, {}).get(key, {}).get("value", default)

    def _set(self, key, typ, value, default, order, description):
        if not(self._section in self._obj):
            self._obj[self._section] = {}
        if self._obj[self._section].has_key(key):
           assert type(self._obj[self._section][key]) == dict
        self._obj[self._section][key] = {
            "type": typ,
            "default": default,
            "description": description,
            "order": order
        }
        if value != default:
            self._obj[self._section][key]["value"] = value

    @staticmethod
    def integer(key, default=0, order=1, description="No description."):
        def getx(self):
            return int(self._get(key, default))
        def setx(self, value):
            self._set(key, "integer", value, default, order, description)
        def delx(self):
            setx(self, default)
        return property(getx, setx, delx, description)

    @staticmethod
    def string(key, default='', order=1, description="No description."):
        def getx(self):
            return self._get(key, default)
        def setx(self, value):
            self._set(key, "string", value, default, order, description)
        def delx(self):
            setx(self, default)
        return property(getx, setx, delx, description)

    @staticmethod
    def boolean(key, default=False, order=1, description="No description."):
        def getx(self):
            value = self._get(key, default)
            if type(value) == str or type(value) == unicode:
                return value.lower() == "true"
            elif type(value) == bool:
                return value
            return False
        def setx(self, value):
            self._set(key, "boolean", value, default, order, description)
        def delx(self):
            setx(self, default)
        return property(getx, setx, delx, description)

    @staticmethod
    def list(key, default=[], order=1, description="No description."):
        def getx(self):
            value = self._get(key, "")
            if type(value) == str or type(value) == unicode:
                value = value.strip()
                if value:
                    return value.split(",")
            elif type(value) == list:
                return value
            return []
        def setx(self, value):
            self._set(key, "list", value, default, order, description)
        def delx(self):
            setx(self, default)
        return property(getx, setx, delx, description)

def fromini(ini):
    """ Create a JSON object from a ini-style config. """
    json = {}
    for section in ini.sections():
        json[section] = {}
        for option in ini.options(section):
            json[section][option] = ini.get(section, option)
    return json

class Connection:

    _MANAGER_CONFIG_CLASS = Config
    _ENDPOINT_CONFIG_CLASS = Config

    def __init__(self, object_class=None, name='', config=None):
        if object_class:
            self._section = "%s:%s" % (object_class, name)
        else:
            self._section = name
        self._name = name
        if config is None:
            self._config = {}
        else:
            self._config = config

    def _manager_config(self, config=None, values=None):
        """ Return the manager config associated with this connection. """
        if config is None:
            config = self._config
        return self._MANAGER_CONFIG_CLASS(obj=config, section=self._section, values=values)

    def _endpoint_config(self, config=None, values=None):
        """ Return the endpoint config associated with the given values. """
        if config is None:
            config = {}
        return self._ENDPOINT_CONFIG_CLASS(obj=config, section=self._section, values=values)
