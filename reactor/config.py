import ConfigParser
from StringIO import StringIO

class Config(object):

    def __init__(self, config_str=''):
        self.default = ConfigParser.SafeConfigParser()
        self.config  = ConfigParser.SafeConfigParser()
        self._load(config_str)
        self.clean = True

    def _get(self, section, key, default):
        # Set the default value.
        if not(self.default.has_section(section)):
            self.default.add_section(section)
        if not(self.default.has_option(section, key)):
            self.default.set(section, key, default)

        # Get the real value.
        if self.config.has_option(section, key):
            return self.config.get(section, key)
        else:
            return default

    def _getint(self, section, key, default):
        try:
            return int(self._get(section, key, str(default)))
        except ValueError:
            return default

    def _getbool(self, section, key, default):
        default = default and "true" or "false"
        return self._get(section, key, default).lower() == "true"

    def _getlist(self, section, key):
        value = self._get(section, key, "").strip()
        if value:
            return value.split(",")
        else:
            return []

    def _set(self, section, key, value):
        if not(self.config.has_section(section)):
            self.config.add_section(section)

        # Check for a same value.
        if self.config.has_option(section, key) and \
            self.config.get(section, key) == value:
            return
        else:
            self.config.set(section, key, value)
            self.clean = False

    def _is_clean(self):
        return self.clean

    def _defaults(self, config_str):
        self.default.readfp(StringIO(config_str))

    def _load(self, config_str):
        self.config.readfp(StringIO(config_str))

    def reload(self, config_str):
        self.config.readfp(StringIO(config_str))

    def __str__(self):
        config_value = StringIO()
        self.default.write(config_value)
        self.config.write(config_value)
        return config_value.getvalue()

class ConfigView(object):

    def __init__(self, config, section):
        self.config  = config
        self.section = section

    def _get(self, key, default):
        return self.config._get(self.section, key, default)

    def __str__(self):
        return str(self.config)

class SubConfig(object):

    def __init__(self, view):
        self.view = view

    def _get(self, key, default):
        return self.view._get(key, default)

    def __str__(self):
        return str(self.view)
