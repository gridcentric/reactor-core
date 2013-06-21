import json

from ConfigParser import SafeConfigParser
from StringIO import StringIO
from collections import namedtuple

ConfigSpec = namedtuple("ConfigSpec", \
    ["type",
     "label",
     "default",
     "normalize",
     "validate",
     "order",
     "description",
     "alternates"])

class Config(object):

    def __init__(self, section='', obj=None, values=None):
        self._section = section
        self._getters = {}
        self._setters = {}
        self._deleters = {}
        self._validation = {}
        self._alternates = {}

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
        defaults = {}
        for k in dir(self):
            if k.startswith('_'):
                continue

            # Ensure it's not one of our types.
            if k in dir(Config):
                continue

            # Pull out the specification.
            # We assume that all the properties have been created using our
            # static methods below. These static methods save a special tuple,
            # which we now pull out and use to create special properties.
            def closure(k, spec):
                def getx(self):
                    value = self._get(k, spec.default)
                    if spec.normalize:
                        value = spec.normalize(value)
                    return value
                def setx(self, value):
                    if spec.normalize:
                        value = spec.normalize(value)
                    self._set(k, spec.type, spec.label, value, spec.default, spec.order, spec.description)
                def delx(self):
                    setx(self, spec.default)
                return (getx, setx, delx)
            spec = getattr(self, k)
            (getx, setx, delx) = closure(k, spec)

            # Remember the validation rules and save the property.
            # NOTE: We don't do any validation on set, because the
            # validation could have some side-effects (and may not 
            # necessarily be ultra quick -- it could reach out and
            # try network connections, etc.)
            self._getters[k] = getx
            self._setters[k] = setx
            self._deleters[k] = delx
            self._validation[k] = spec.validate
            if spec.alternates:
                for alt in spec.alternates:
                    self._alternates[alt] = k
            defaults[k] = spec.default

        for k in self._obj.get(self._section, {}).keys():
            if k in self._alternates:
                # Move the underlying spec.
                self._obj[self._section][self._alternates[k]] = self._obj[self._section][k]
                del self._obj[self._section][k]

        for k,v in defaults.items():
            if len(self._get_obj(k)) == 0:
                # Populate the default value.
                setattr(self, k, v)

        if values:
            # Populate the given values.
            self._update(values)

    def __getattribute__(self, name):
        if name.startswith('_'):
            return object.__getattribute__(self, name)
        else:
            try:
                return self._getters[name](self)
            except KeyError:
                # This special case exists only for the
                # initial setup. We may not have actually
                # finished setting up all the getters, so
                # we just fall back to getting the class
                # definition (for the specifications).
                return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        elif name in self._setters:
            self._setters[name](self, value)
        else:
            raise AttributeError(name)

    def __delattr__(self, name):
        if name.startswith('_'):
            object.__delattr__(self, name)
        elif name in self._deleters:
            self._deleters[name](self)
        else:
            raise AttributeError(name)

    def _get_obj(self, key, section=None):
        if section == None:
            section = self._section
        if not self._obj.has_key(section):
            self._obj[section] = {}
        if not self._obj[section].has_key(key):
            self._obj[section][key] = {}
        return self._obj[section][key]

    def _update(self, obj):
        obj = fromstr(obj)
        for name,section in obj.items():
            for k,v in section.items():
                # Set the value always.
                if k in self._alternates:
                    k = self._alternates[k]
                self._get_obj(k, section=name)["value"] = v

    def _spec(self):
        """ The underlying specification and values. """
        return self._obj

    def _values(self):
        """ The set of all configuration values. """
        rval = {}
        for name,section in self._obj.items():
            rval[name] = {}
            for k,v in section.items():
                if v.get("value") and v.get("default") != v.get("value"):
                    rval[name][k] = v.get("value")
        return rval

    def _validate(self):
        errors = {}
        for k,fn in self._validation.items():
            if fn:
                try:
                    fn(self)
                except Exception, e:
                    self._add_error(k, str(e))

    def _add_error(self, k, errmsg):
        """ Annotate the specification with a validation error. """
        # Save the given error message.
        self._get_obj(k)["error"] = errmsg

    def _validate_errors(self):
        """ The set of all validation errors (organized as values). """
        result = {}
        for name,section in self._obj.items():
            for k,v in section.items():
                errmsg = v.get("error")
                if errmsg:
                    if not result.has_key(name):
                        result[name] = {}
                    result[name][k] = errmsg
        if result:
            return result
        else:
            return None

    def _get(self, key, default):
        return self._get_obj(key).get("value", default)

    def _set(self, key, typ, label, value, default, order, description):
        self._get_obj(key).update([
            ("type", typ),
            ("label", label),
            ("default", default),
            ("description", description),
            ("order", order),
            ("value", value)
        ])

    @staticmethod
    def error(reason):
        raise Exception(reason)

    @staticmethod
    def integer(label=None, default=0, order=1, validate=None, description="No description.", alternates=None):
        return ConfigSpec("integer", label, default, int, validate, order, description, alternates)

    @staticmethod
    def string(label=None, default='', order=1, validate=None, description="No description.", alternates=None):
        return ConfigSpec("string", label, default, lambda s: s and str(s) or None, validate,
                order, description, alternates)

    @staticmethod
    def boolean(label=None, default=False, order=1, validate=None, description="No description.", alternates=None):
        def normalize(value):
            if type(value) == str or type(value) == unicode:
                return value.lower() == "true"
            elif type(value) == bool:
                return value
            return False
        return ConfigSpec("boolean", label, default, normalize, validate, order, description, alternates)

    @staticmethod
    def list(label=None, default=[], order=1, validate=None, description="No description.", alternates=None):
        def normalize(value):
            if type(value) == str or type(value) == unicode:
                value = value.strip()
                if value:
                    return value.split(",")
            elif type(value) == list:
                return value
            return []
        return ConfigSpec("list", label, default, normalize, validate, order, description, alternates)

def fromini(ini):
    """ Create a JSON object from a ini-style config. """
    json = {}
    for section in ini.sections():
        json[section] = {}
        for option in ini.options(section):
            json[section][option] = ini.get(section, option)
    return json

def fromstr(obj):
    """ Create a JSON object from an arbitrary string. """
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
    return obj

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
