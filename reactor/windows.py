import base64
import datetime
import logging
import os
import random
import re
import time
import uuid

import ldap
import ldap.modlist as modlist

from reactor.config import Config
from reactor.config import Connection

COMPUTER_ATTRS = [
    "operatingsystem",
    "countrycode",
    "cn",
    "lastlogoff",
    "dscorepropagationdata",
    "usncreated",
    "objectguid",
    "iscriticalsystemobject",
    "serviceprincipalname",
    "whenchanged",
    "localpolicyflags",
    "accountexpires",
    "primarygroupid",
    "badpwdcount",
    "objectclass",
    "instancetype",
    "objectcategory",
    "whencreated",
    "lastlogon",
    "useraccountcontrol",
    "samaccountname",
    "operatingsystemversion",
    "samaccounttype",
    "adspath",
    "serverreferencebl",
    "dnshostname",
    "pwdlastset",
    "ridsetreferences",
    "logoncount",
    "codepage",
    "name",
    "usnchanged",
    "badpasswordtime",
    "objectsid",
    "distinguishedname",
]

COMPUTER_RECORD = {
    'objectclass' : ['top', 'person', 'organizationalPerson', 'user', 'computer'],
}

PASSWORD_ALPHABET = "abcdefghijklmnmoqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" + \
    "0123456789 `~!@#$%^&*()_-+={}[]\|:;\"'<>,.?/"

def generate_password(length=18, alpha=PASSWORD_ALPHABET):
    alpha_len = len(alpha)
    return "".join([ alpha[ord(byte) % alpha_len] for byte in os.urandom(length) ])

def _wrap_and_retry(fn):
    def _wrapped_fn(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except ldap.LDAPError:
            self.con = None
            return fn(self, *args, **kwargs)
    _wrapped_fn.__name__ = fn.__name__
    _wrapped_fn.__doc__ = fn.__doc__
    return _wrapped_fn

class LdapConnection:
    def __init__(self, domain, username, password, orgunit='', host=None):
        self.domain   = domain
        self.username = username
        self.password = password
        self.orgunit  = orgunit
        if not host:
            self.host = domain
        else:
            self.host = host
        self.con      = None

    def _open(self):
        if not(self.con):
            ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
            self.con = ldap.initialize("ldaps://%s:636" % self.host)
            self.con.set_option(ldap.OPT_REFERRALS, 0)
            self.con.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
            self.con.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_DEMAND)
            self.con.set_option(ldap.OPT_X_TLS_DEMAND, True)
            self.con.simple_bind_s("%s@%s" % (self.username, self.domain), self.password)
        return self.con

    def __del__(self):
        try:
            if self.con:
                self.con.unbind()
        except:
            pass

    # Returns the properly formatted "ou=," string.
    def _orgpath_from_ou(self):
        if self.orgunit:
            orgpath = self.orgunit.split("\\")
            orgpath.reverse()
            ou = ",".join(map(lambda x: 'ou=%s' % x, orgpath))
            return ou
        else:
            return "cn=Computers"

    # Returns the properly formatted "dc=," string.
    def _dom_from_domain(self):
        return ",".join(map(lambda x: 'dc=%s' % x, self.domain.split(".")))

    def _machine_description(self, name=None):
        dom      = self._dom_from_domain()
        ou       = self._orgpath_from_ou()
        if name:
            return "cn=%s,%s,%s" % (name, ou, dom)
        else:
            return "%s,%s" % (ou, dom)

    @_wrap_and_retry
    def list_machines(self, name=None, attrs=COMPUTER_ATTRS):
        filter   = '(objectclass=computer)'
        desc     = self._machine_description(name)
        machines = self._open().search_s(desc, ldap.SCOPE_SUBTREE, filter, attrs)
        rval     = {}

        # Synthesize the machines into a simple form.
        for machine in machines:
            if machine[0]:
                for cn in machine[1]['cn']:
                    rval[cn.lower()] = machine[1]
        return rval

    def check_logged_on(self, machine):
        lastLogoff = int(machine.get('lastLogoff', ['0'])[0])
        lastLogon  = int(machine.get('lastLogon', ['0'])[0])
        if lastLogon > lastLogoff:
            return True
        else:
            return False

    def check_dead(self, machine):
        # Compute expiry (one month in the past).
        now = datetime.datetime.now()
        expiry = datetime.datetime(now.year, now.month-1, now.day,
                                   now.hour, now.minute, now.second)

        # Check the last update time.
        changed = machine.get('whenChanged', [''])[0]
        m = re.match("(\d\d\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d).\d*Z", changed)
        if m:
            dt = datetime.datetime(int(m.group(1)),
                                   int(m.group(2)),
                                   int(m.group(3)),
                                   int(m.group(4)),
                                   int(m.group(5)),
                                   int(m.group(6)))

            if dt > expiry:
                return False

        # Check the last logon time.
        lastLogon = int(machine.get('lastLogon', ['0'])[0])
        dt = datetime.datetime.fromtimestamp(lastLogon / 1000000)
        if dt > expiry:
            return False

        return True

    # Removes a machine from the LDAP directory
    @_wrap_and_retry
    def remove_machine(self, machine):
        connection = self._open()
        try:
            connection.delete_s(machine['distinguishedName'][0])
        except:
            # Ignore, as long as we can create a new account we are okay.
            pass

    @_wrap_and_retry
    def clean_machines(self, template):
        template = template.replace("#", "\d")
        machines = self.list_machines()

        for (name, machine) in machines.items():
            if re.match(template, name):
                if not(self.check_logged_on(machine)) or \
                    self.check_dead(machine):
                    self.remove_machine(machine)

    @_wrap_and_retry
    def create_machine(self, template):
        # we only care about machine names, so limit the attributes
        # set returned, for performance.
        machines = self.list_machines(attrs=['cn'])
        index = template.find("#")
        if index < 0:
            return False

        # Extract a maximum substring.
        size = 1
        while template[index:index+size] == ("#" * size):
            size += 1
        size -= 1

        # Compute an integer in the range we want.
        fmt = "%%0%sd" % size
        maximum = pow(10, size)
        n = 1
        while n < maximum:
            # Find the next unused machine name that fits template
            name = template.replace("#" * size, fmt % n)
            if not(name.lower() in machines):
                break
            n = n + 1

            # Fail out if we've run out of machine names.
            if n == maximum:
                return False

        # Generate a password.
        password = generate_password()
        quoted_password = '"' + password + '"'
        utf_password = password.encode('utf-16-le')
        utf_quoted_password = quoted_password.encode('utf-16-le')
        base64_password = base64.b64encode(utf_password)

        # Generate the queries for creating the account.
        # NOTE: We aggressively cast here to ensure that
        # all the values are bare strings, not unicode.
        # The python ldap library tends to throw up all
        # over the place when it gets some unicode values.
        new_record = {}
        new_record.update(COMPUTER_RECORD.items())
        new_record['cn']             = str(name.upper())
        new_record['description']    = str('')
        new_record['dNSHostName']    = str('%s.%s' % (name, self.domain))
        new_record['sAMAccountName'] = str('%s$' % name)
        new_record['servicePrincipalName'] = [
            str('HOST/%s' % name.upper()),
            str('HOST/%s.%s' % (name, self.domain)),
            str('TERMSRV/%s' % name.upper()),
            str('TERMSRV/%s.%s' % (name, self.domain)),
            str('RestrictedKrbHost/%s' % name.upper()),
            str('RestrictedKrbHost/%s.%s' % (name, self.domain))
        ]
        new_record['unicodePwd'] = str(utf_quoted_password)
        new_record['userAccountControl'] = str('4096') # Enable account.

        descr = self._machine_description(name)
        connection = self._open()

        # Create the new account.
        connection.add_s(descr, modlist.addModlist(new_record))

        return (name, base64_password)

class WindowsConfig(Config):

    # Our cached connection.
    _connection = None

    domain = Config.string("domain", order=0,
        description="The Windows domain.")

    username = Config.string("username", order=1,
        description="An Administrator within the domain.")

    password = Config.string("password", order=2,
        description="The Administrator password.")

    orgunit = Config.string("orgunit", order=3,
        description="The orgunit for new machines.")

    template = Config.string("template", default="windowsVM######", order=4,
        description="The template machine name for new machines.")

    host = Config.string("host", order=5,
        description="The AD server to contact.")

    def _get_connection(self):
        if not(self.domain):
            return None
        if self._connection is None:
            self._connection = LdapConnection(self.domain,
                                              self.username,
                                              self.password,
                                              self.orgunit,
                                              self.host)
        return self._connection

    def _validate(self):
        Config._validate(self)
        assert len(self.template) == 15
        conn = self._get_connection()
        if conn:
            # If we have a connection (i.e. the user has
            # specified a windows domain in their config)
            # then we ensure that we can connect.
            conn._open()
            del conn

class WindowsConnection(Connection):

    _ENDPOINT_CONFIG_CLASS = WindowsConfig

    def __init__(self, **kwargs):
        Connection.__init__(self, object_class=None, **kwargs)

    def start_params(self, config):
        config = self._endpoint_config(config)
        connection = config._get_connection()
        if not connection:
            return {}

        # Create a new machine accout.
        info = connection.create_machine(config.template)
        if info:
            logging.info("Created new machine account %s" % info[0])
            # Return the relevant information about the machine.
            return { "name" : info[0], "machinepassword" : info[1] }
        else:
            return {}

    def cleanup(self, config, name):
        config = self._endpoint_config(config)
        connection = config._get_connection()
        if connection:
            try:
                # Look for machine that matches the name.
                machines = connection.list_machines(name)
                connection.remove_machine(machines[name])
            except:
                logging.warn("Unable to remove machine account %s" % name)
            else:
                logging.info("Removed machine account %s" % name)

    def cleanup_start_params(self, config, start_params):
        # Extract name from start_params.
        name = start_params.get("name")
        if name:
            self.cleanup(config, name)
