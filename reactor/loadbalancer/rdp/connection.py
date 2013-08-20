import base64
import datetime
import logging
import os
import re

import ldap
import ldap.modlist as modlist
ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
from ldap.controls import SimplePagedResultsControl

from reactor.config import Config

from reactor.loadbalancer.backend import Backend
from reactor.loadbalancer.tcp.connection import TcpEndpointConfig
from reactor.loadbalancer.tcp.connection import Connection as TcpConnection

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

PASSWORD_ALPHABET = "abcdefghijklmnmopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" + \
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

    def __init__(self,
                 domain,
                 username,
                 password,
                 orgunit='',
                 host=None,
                 use_ssl=False):
        self.domain = domain
        self.username = username
        self.password = password
        self.orgunit = orgunit
        if not host:
            self.host = domain
        else:
            self.host = host
        self.use_ssl = use_ssl
        self.con = None

    def open(self):
        if not(self.con):
            if self.use_ssl:
                self.con = ldap.initialize("ldaps://%s:636" % self.host)
                self.con.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_DEMAND)
                self.con.set_option(ldap.OPT_X_TLS_DEMAND, True)
            else:
                self.con = ldap.initialize("ldap://%s:389" % self.host)
            self.con.set_option(ldap.OPT_REFERRALS, 0)
            self.con.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
            self.con.simple_bind_s("%s@%s" % (self.username, self.domain), self.password)
        return self.con

    def __del__(self):
        try:
            if self.con:
                self.con.unbind()
        except Exception:
            pass

    # Returns the properly formatted "ou=," string.
    def orgpath_from_ou(self):
        if self.orgunit:
            orgpath = self.orgunit.split("\\")
            orgpath.reverse()
            ou = ",".join(map(lambda x: 'ou=%s' % x, orgpath))
            return ou
        else:
            return "cn=Computers"

    # Returns the properly formatted "dc=," string.
    def dom_from_domain(self):
        return ",".join(map(lambda x: 'dc=%s' % x, self.domain.split(".")))

    def machine_description(self, name=None):
        dom = self.dom_from_domain()
        ou = self.orgpath_from_ou()
        if name:
            return "cn=%s,%s,%s" % (name, ou, dom)
        else:
            return "%s,%s" % (ou, dom)

    @_wrap_and_retry
    def list_machines(self, name=None, attrs=None):
        if attrs is None:
            attrs = COMPUTER_ATTRS

        filter = '(objectclass=computer)'
        desc = self.machine_description(name)
        page_size = 64
        lc = SimplePagedResultsControl(
            ldap.LDAP_CONTROL_PAGE_OID, True, (page_size,''))
        conn = self.open()
        msgid = conn.search_ext(
            desc, ldap.SCOPE_SUBTREE, filter, attrs, serverctrls=[lc])
        rval = {}

        while True:
            rtype, rdata, rmsgid, serverctrls = conn.result3(msgid)

            # Synthesize the machines into a simple form.
            for machine in rdata:
                if machine[0]:
                    for cn in machine[1]['cn']:
                        rval[cn.lower()] = machine[1]

            # Read the next page of the result.
            pctrls = [ c for c in serverctrls if c.controlType == ldap.LDAP_CONTROL_PAGE_OID ]
            if pctrls:
                est, cookie = pctrls[0].controlValue
                if cookie:
                    lc.controlValue = (page_size, cookie)
                    msgid = conn.search_ext(
                        desc, ldap.SCOPE_SUBTREE, filter, attrs, serverctrls=[lc])
                else:
                    break

        return rval

    def check_logged_on(self, machine):
        last_logoff = int(machine.get('lastLogoff', ['0'])[0])
        last_logon  = int(machine.get('lastLogon', ['0'])[0])
        if last_logon > last_logoff:
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
        last_logon = int(machine.get('lastLogon', ['0'])[0])
        dt = datetime.datetime.fromtimestamp(last_logon / 1000000)
        if dt > expiry:
            return False

        return True

    # Removes a machine from the LDAP directory
    @_wrap_and_retry
    def remove_machine(self, machine):
        connection = self.open()
        try:
            connection.delete_s(machine['distinguishedName'][0])
        except Exception:
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

        # Generate a password.
        password = generate_password()
        quoted_password = '"' + password + '"'
        utf_password = password.encode('utf-16-le')
        utf_quoted_password = quoted_password.encode('utf-16-le')
        base64_password = base64.b64encode(utf_password)

        # To create our new machine, we use a loop retry if we get an
        # exception indicating that the chosen name already exists.
        # This structure is for the following reasons:
        #
        # - In ActiveDirectory, Organizational Units (OU) are for
        # organizing and applying different policies to different
        # groups.  Names of users and machines must be unique under
        # the entire domain, regardless of their OU placement.  Since
        # our machine list query is only under this OU (optimistic),
        # our machine name create may still fail if there is another
        # machine with the same name somewhere else in the domain.
        #
        # - In the machine list query, we do not query the entire list
        # of all machines in the domain because (1) the list can be
        # huge in a large domain and take a significant amount of time
        # to query, and (2) the credentials used may only have access
        # to this OU and not be able to query all names in the domain.
        #
        # - The AD server is the database authority providing atomic
        # transactions, so this loop protects against possible races
        # to create the same name.
        n = 1
        while True:
            # Compute an integer in the range we want.
            fmt = "%%0%sd" % size
            maximum = pow(10, size)
            while n < maximum:
                # Find the next unused machine name that fits template
                name = template.replace("#" * size, fmt % n)
                if not(name.lower() in machines):
                    break
                n = n + 1

                # Fail out if we've run out of machine names.
                if n == maximum:
                    return False

            try:
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

                descr = self.machine_description(name)
                connection = self.open()

                try:
                    # Create the new account.
                    full_record = dict(new_record.items())
                    full_record['unicodePwd'] = str(utf_quoted_password)
                    full_record['userAccountControl'] = '4096' # Enable account.
                    connection.add_s(descr, modlist.addModlist(full_record))

                except ldap.UNWILLING_TO_PERFORM:
                    # On some ADs, they refues to add an account
                    # with the password set and account enabled.
                    # Although it's not as clean -- we are forced
                    # to do it in try stages here.

                    # Create the new account.
                    # NOTE: If this throws an exception we let it
                    # raise up and it'll be handled by the caller.
                    connection.add_s(descr, modlist.addModlist(new_record))

                    try:
                        # Set the account password.
                        password_change_attr = [
                            (ldap.MOD_REPLACE, 'unicodePwd', str(utf_quoted_password))]
                        connection.modify_s(descr, password_change_attr)

                        # Enable the computer account.
                        account_enabled_attr = [
                            (ldap.MOD_REPLACE, 'userAccountControl', '4096')]
                        connection.modify_s(descr, account_enabled_attr)
                    except:
                        self.remove_machine(name)

            except ldap.ALREADY_EXISTS:
                machines[name.lower()] = name.lower()
                continue # repeat the process, optimistically.

            # success. don't loop.
            break

        return (name, base64_password)

class RdpEndpointConfig(TcpEndpointConfig):

    def __init__(self, **kwargs):
        super(RdpEndpointConfig, self).__init__(**kwargs)
        self._connection = None

    domain = Config.string(label="Active Directory Domain", order=0,
        validate=lambda self: self.check_credentials(),
        description="Fully-qualified name of the Active Directory domain for " +
        "the VM machine accounts.")

    username = Config.string(label="Active Directory Username", order=1,
        description="An Administrator within the domain.")

    password = Config.string(label="Active Directory Password", order=2,
        description="The Administrator password.")

    orgunit = Config.string(label="Active Directory Orginational Unit", order=3,
        description="The orgunit for new machines. The master machine account " +
        "must be in the same orgunit prior to live-imaging.")

    template = Config.string(label="Machine Name Template",
        default="windowsVM######", order=4,
        validate=lambda self: len(self.template) == 15 or \
            Config.error("Template must be 15 characters long."),
        description="The template machine name for new machines.")

    host = Config.string(label="Domain Controller", order=5,
        validate=lambda self: self.check_connection(),
        description="The network address (hostname or IP) of the AD server to contact.")

    use_ssl = Config.boolean(label="Use SSL", order=6,
        description="Whether or not to use SSL for Ldap communication.")

    def ldap_connection(self):
        if not(self.domain):
            return None
        if self._connection is None:
            self._connection = LdapConnection(self.domain,
                                              self.username,
                                              self.password,
                                              orgunit=self.orgunit,
                                              host=self.host,
                                              use_ssl=self.use_ssl)
        return self._connection

    def check_credentials(self):
        try:
            self.check_connection(False)
        except ldap.INVALID_CREDENTIALS:
            Config.error("Invalid credentials")
        except Exception as e:
            Config.error("Unknown exception: %s" % repr(e))

    def check_connection(self, hostcheck=True):
        try:
            self.try_connection()
        except ldap.SERVER_DOWN:
            if hostcheck:
                Config.error("Could not connect to host")
        except Exception as e:
            # If we're not just validating the host, propagate
            if not hostcheck:
                raise e

    def try_connection(self):
        conn = self.ldap_connection()
        self._connection = None
        if conn:
            # If we have a connection (i.e. the user has
            # specified a windows domain in their config)
            # then we ensure that we can connect.
            conn.open()

class Connection(TcpConnection):

    """ Remote Desktop Protocol """

    _ENDPOINT_CONFIG_CLASS = RdpEndpointConfig
    _SUPPORTED_URLS = {
        # We return an expression compatible with the
        # TCP loadbalancer. We accept a port, but we'll
        # return the default port of 3389.
        "(rdp://([1-9][0-9]*|)|)" : lambda m: int(m.group(2) or 3389)
    }

    def start_params(self, config):
        config = self._endpoint_config(config)
        connection = config.ldap_connection()
        if not connection:
            return {}

        # Create a new machine accout.
        info = connection.create_machine(config.template)
        if info:
            logging.info("Created new machine account %s", info[0])
            # Return the relevant information about the machine.
            return { "name" : info[0], "machinepassword" : info[1] }
        else:
            return {}

    def cleanup(self, config, name):
        config = self._endpoint_config(config)
        connection = config.ldap_connection()
        if connection:
            try:
                # Look for machine that matches the name.
                machines = connection.list_machines(name)
                connection.remove_machine(machines[name])
            except Exception:
                logging.warn("Unable to remove machine account %s", name)
            else:
                logging.info("Removed machine account %s", name)

    def cleanup_start_params(self, config, start_params):
        # Extract name from start_params.
        name = start_params.get("name")
        if name:
            self.cleanup(config, name)

    def change(self, url, ips, **kwargs):
        # Update the backend port to be the sensible RDP default, instead
        # of default to whatever port we're listening on here.
        ips = [Backend(ip.ip, ip.port or 3389, ip.weight) for ip in ips]
        return super(Connection, self).change(url, ips, **kwargs)
