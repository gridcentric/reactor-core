# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import hashlib
import json
import logging
import traceback
import ConfigParser

from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.security import remember, forget, authenticated_userid
from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from paste import httpserver

from . import cli
from . import utils
from . import server
from . import defaults
from . import ips as ips_mod
from . log import log
from . atomic import Atomic
from . config import fromstr
from . manager import ManagerConfig
from . manager import ManagerLog
from . endpoint import EndpointConfig
from . endpoint import EndpointLog
from . objects.root import Reactor
from . objects.endpoint import EndpointExists
from . objects.endpoint import EndpointNotFound
from . zookeeper.connection import ZookeeperException
from . zookeeper.client import ZookeeperClient

def authorized(forbidden_view=None, allow_endpoint=False):
    """
    A Decorator that does a simple check to see if the request is
    authorized before executing the actual handler.

    Use of this decorator implies use of the @connected decorator.
    (This is implicit as we will definitely call functions that we
    be decorated with @connected(). We don't force this here.)
    """
    def decorator(request_handler):
        def fn(self, context, request, **kwargs):
            try:
                # Make this implict routes are matched.
                self.authorize_ip_access(context, request)
            except Exception, e:
                return Response(status=401, body=str(e))

            # Can we authorize as an admin?
            if self.authorize_admin_access(context, request):
                return request_handler(self, context, request, **kwargs)

            # Can we authorize as an endpoint?
            if (allow_endpoint and
                self.authorize_endpoint_access(context, request)):
                return request_handler(self, context, request, **kwargs)

            # Access denied.
            if forbidden_view is not None:
                return eval(forbidden_view)(context, request)
            else:
                # Return an unauthorized response.
                return Response(status=401, body="unauthorized")
        fn.__name__ = request_handler.__name__
        fn.__doc__ = request_handler.__doc__
        return fn

    return decorator

def connected(fn):
    """
    A decorator that ensures we are connected to the Zookeeper server.

    Additionally, this decorator will disconnect from the server on any
    unexpected exception. This is useful to ensure that we don't get stuck with
    a stale connection, retrying to the same calls over and over.
    """
    def try_once(self, *args, **kwargs):
        try:
            self.connect()
            return fn(self, *args, **kwargs)
        except EndpointExists, e:
            # Already exists.
            return Response(status=409, body=str(e))
        except EndpointNotFound, e:
            # Couldn't find object.
            return Response(status=404, body=str(e))
        except ZookeeperException:
            # Disconnect (next request will reconnect).
            logging.error("Unexpected error: %s", traceback.format_exc())
            self.disconnect()
            return None
    def wrapper_fn(*args, **kwargs):
        response = try_once(*args, **kwargs)
        if response is None:
            response = try_once(*args, **kwargs)
        if response is None:
            return Response(status=500, body="internal error")
        else:
            return response
    wrapper_fn.__name__ = fn.__name__
    wrapper_fn.__doc__ = fn.__doc__
    return wrapper_fn

class ReactorApi(Atomic):

    AUTH_SALT = 'gridcentricreactor'

    def __init__(self, zk_servers):
        super(ReactorApi, self).__init__()
        self.client = ZookeeperClient(zk_servers)
        self.zkobj = Reactor(self.client)
        self.config = Configurator()
        self._endpoints_zkobj = self.zkobj.endpoints()

        # Set up auth-ticket authentication.
        self.config.set_authentication_policy(
            AuthTktAuthenticationPolicy(
                self.AUTH_SALT))
        self.config.set_authorization_policy(
            ACLAuthorizationPolicy())

        # Setup basic version route.
        self.config.add_route('version', '/')
        self.config.add_view(self.version,
            route_name='version', accept='application/json')

        # Add authentication routes.
        self._add('login', ['1.1'], 'login', self.login)
        self._add('logout', ['1.1'], 'logout', self.logout)

        self._add('auth-key', ['1.0', '1.1'],
                  'auth_key', self.set_auth_key)

        self._add('domain-action', ['1.0'],
                  'domain', self.handle_domain_action)

        self._add('url', ['1.1'],
                  'url', self.handle_url_action)

        self._add('info', ['1.1'],
                  'info', self.handle_info_action)

        self._add('register-implicit', ['1.0', '1.1'],
                  'register', self.register_ip_implicit)
        self._add('register', ['1.0', '1.1'],
                  'register/{endpoint_ip}', self.register_ip_address)

        self._add('unregister-implicit',  ['1.0', '1.1'],
                  'unregister', self.unregister_ip_implicit)
        self._add('unregister',  ['1.0', '1.1'],
                  'unregister/{endpoint_ip}', self.unregister_ip_address)

        self._add('manager-config-action',  ['1.0', '1.1'],
                  'managers/configs/{manager}', self.handle_manager_config_action)

        self._add('manager-config-list',  ['1.0', '1.1'],
                  'managers/configs', self.list_manager_configs)

        self._add('manager-active-action',  ['1.0', '1.1'],
                  'managers/active/{manager}', self.handle_manager_active_action)

        self._add('manager-active-list',  ['1.0', '1.1'],
                  'managers/active', self.list_managers_active)

        self._add('manager-active-log', ['1.1'],
                  'managers/log/{manager}', self.handle_manager_log)

        self._add('endpoint-action',  ['1.0', '1.1'],
                  'endpoints/{endpoint_name}', self.handle_endpoint_action)
        self._add('endpoint-action-implicit',  ['1.0', '1.1'],
                  'endpoint', self.handle_endpoint_action)

        self._add('endpoint-alias-action',  ['1.1'],
                  'endpoints/{endpoint_name}/alias', self.handle_alias_action)
        self._add('endpoint-alias-action-implicit',  ['1.1'],
                  'endpoint/alias', self.handle_alias_action)

        self._add('endpoint-list',  ['1.0', '1.1'],
                  'endpoints', self.list_endpoints)

        self._add('endpoint-ip-list', ['1.0', '1.1'],
                  'endpoints/{endpoint_name}/ips', self.list_endpoint_ips)
        self._add('endpoint-ip-list-implicit', ['1.0', '1.1'],
                  'endpoint/ips', self.list_endpoint_ips)

        self._add('metric-action', ['1.0', '1.1'],
                  'endpoints/{endpoint_name}/metrics', self.handle_metric_action)
        self._add('metric-action-implicit', ['1.0', '1.1'],
                  'endpoint/metrics', self.handle_metric_action)

        self._add('metric-ip-action', ['1.0', '1.1'],
                  'endpoints/{endpoint_name}/metrics/{endpoint_ip}', self.handle_metric_action)
        self._add('metric-ip-action-implicit', ['1.0', '1.1'],
                  'endpoint/metrics/{endpoint_ip}', self.handle_metric_action)

        self._add('endpoint-state-action', ['1.0', '1.1'],
                  'endpoints/{endpoint_name}/state', self.handle_state_action)
        self._add('endpoint-state-action-implicit', ['1.0', '1.1'],
                  'endpoint/state', self.handle_state_action)

        self._add('endpoint-log', ['1.1'],
                  'endpoints/{endpoint_name}/log', self.handle_log_action)
        self._add('endpoint-log-implicit', ['1.1'],
                  'endpoint/log', self.handle_log_action)

        self._add('session-list', ['1.1'],
                  'endpoints/{endpoint_name}/sessions', self.list_sessions)
        self._add('session-list-implicit', ['1.1'],
                  'endpoint/sessions', self.list_sessions)

        self._add('session-action', ['1.1'],
                  'endpoints/{endpoint_name}/sessions/{session}', self.handle_session_action)
        self._add('session-action-implicit', ['1.1'],
                  'endpoint/sessions/{session}', self.handle_session_action)

        self._add('instance-list', ['1.1'],
                  'endpoints/{endpoint_name}/instances', self.list_instances)
        self._add('instance-list-implicit', ['1.1'],
                  'endpoint/instances', self.list_instances)

        self._add('instance-action', ['1.1'],
                  'endpoints/{endpoint_name}/instances/{instance_id}', self.handle_instance_action)
        self._add('instance-action-implicit', ['1.1'],
                  'endpoint/instances/{instance_id}', self.handle_instance_action)

        self._add('metadata-list', ['1.1'],
                  'endpoints/{endpoint_name}/metadata', self.list_metadata)
        self._add('metadata-list-implicit', ['1.1'],
                  'endpoint/metadata', self.list_metadata)

        self._add('metadata-action', ['1.1'],
                  'endpoints/{endpoint_name}/metadata/{key_name}', self.handle_metadata_action)
        self._add('metadata-action-implicit', ['1.1'],
                  'endpoint/metadata/{key_name}', self.handle_metadata_action)

    def _add(self, name, versions, path, fn):
        for version in versions:
            route_name = "%s:%s" % (version, name)
            url_path = "/v%s/%s" % (version, path)
            self.config.add_route(route_name, url_path)
            self.config.add_view(fn,
                route_name=route_name, accept="application/json")

    def disconnect(self):
        self.client.disconnect()

    def connect(self):
        self.client.connect()

    def _endpoint_name_for_ip(self, ip):
        uuid = self.zkobj.endpoint_ips().get(ip)
        if uuid:
            endpoint_names = self.zkobj.endpoints().get_names(uuid)
            if endpoint_names and len(endpoint_names) > 0:
                return endpoint_names[0]
        return None

    def servers(self):
        return self.client.servers()

    def get_wsgi_app(self):
        return self.config.make_wsgi_app()

    @connected
    def authorize_admin_access(self, context, request):
        if self.zkobj.auth_hash is not None:
            if authenticated_userid(request) is not None:
                return True
            auth_hash = self._create_admin_auth_token(self._req_get_auth_key(request))
            return (self.zkobj.auth_hash == auth_hash)
        else:
            # If there is no auth hash then authentication has not
            # been turned on so all requests are allowed by default.
            return True

    def _req_get_auth_key(self, request):
        return request.headers.get('X-Auth-Key', None) or \
               request.params.get('auth_key', None)

    @connected
    def authorize_endpoint_access(self, context, request):
        # Pull an endpoint name if it is specified.
        endpoint_name = request.matchdict.get('endpoint_name', None)

        # Pull an endpoint name via the endpoint IP.
        if endpoint_name is None:
            endpoint_ip = request.matchdict.get('endpoint_ip', None)
            if endpoint_ip is not None:
                # Pull out the endpoint name for the given ip address.
                # NOTE: This set of ip addresses does not include static
                # address -- this is for security reasons. You can't add
                # arbitrary IPs to your endpoint by simply changing your
                # configuration.
                endpoint_name = self._endpoint_name_for_ip(endpoint_ip)

        if endpoint_name is None:
            return False

        # Parse authentication details.
        endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
        endpoint_config = EndpointConfig(values=endpoint.get_config())
        auth_hash, auth_salt, auth_algo = \
            endpoint_config.endpoint_auth()

        if auth_hash is not None and auth_hash != "":
            auth_key = self._req_get_auth_key(request)
            if auth_key is not None:
                auth_token = self._create_endpoint_auth_token(\
                    auth_key, auth_salt, auth_algo)
                return (auth_hash == auth_token)
            else:
                # An auth_hash was set on the endpoint,
                # and the user did not provide one.
                return False

        # We were not able to authenticate using the
        # credentials from any endpoint associated with
        # this ip address. We allow access if this was an
        # implicit match (i.e. the endpoint name was set
        # because it was from the IP) otherwise we disallow.
        if request.matched_route is not None:
            return request.matched_route.name.endswith("-implicit")
        else:
            return False

    @connected
    def _extract_remote_ip(self, context, request):
        # NOTE(dscannell): The remote ip address is taken from the
        # request.environ['REMOTE_ADDR']. This value may need to be added by
        # some WSGI middleware depending on what webserver fronts this app.
        ip_address = request.environ.get('REMOTE_ADDR', "")
        forwarded_for = request.headers.get('X-Forwarded-For', "")

        # We may be running the API behind scale managers. We don't want to
        # necessarily trust the X-Forwarded-For header that the client passes,
        # but if we've been forwarded from an active manager then we can assume
        # that this header has been placed by a trusted middleman.
        if forwarded_for and \
            (ips_mod.is_local(ip_address) or \
            ip_address in self.zkobj.managers().list_configs()):
            ip_address = forwarded_for

        return ip_address

    @connected
    def authorize_ip_access(self, context, request):
        matched_route = request.matched_route
        if matched_route is not None:
            if matched_route.name.endswith("-implicit"):
                # We can only do ip authorizing on implicit routes. Essentially
                # we will update the request to confine it to the endpoint with
                # this address.
                request_ip = self._extract_remote_ip(context, request)
                endpoint_name = self._endpoint_name_for_ip(request_ip)
                if endpoint_name:
                    # Authorize this request and set the endpoint_name.
                    request.matchdict['endpoint_name'] = endpoint_name
                    request.matchdict['endpoint_ip'] = request_ip
                    return True
                else:
                    raise Exception("Must query from endpoint ip.")

        return False

    def _create_admin_auth_token(self, auth_key):
        if auth_key is not None:
            # NOTE: We use a fixed salt and force sha1 for the admin token.
            # This fixed salt matches the authentication policy used above.
            return utils.sha_hash("%s%s" % (self.AUTH_SALT, auth_key))
        else:
            return None

    def _create_endpoint_auth_token(self, auth_key, auth_salt, algo):
        if auth_salt is None:
            auth_salt = ""
        salted = "%s%s" % (auth_salt, auth_key)
        if not algo:
            return salted
        else:
            try:
                hasher = hashlib.new(algo, salted)
                return hasher.hexdigest()
            except Exception:
                logging.warn("Failed to authenticate against endpoint.")
                return None

    def index(self, context, request):
        return Response()

    @log
    @connected
    def version(self, context, request):
        """
        Get the version implemented by this API.
        """
        if request.method == "GET":
            if 'json' in request.headers.get('Accept'):
                return Response(body=json.dumps({'version': '1.1'}))
            else:
                return self.index(context, request)
        else:
            return Response(status=403)

    @log
    def login(self, context, request):
        """
        Logs the admin user in.
        """
        auth_key = self._req_get_auth_key(request)
        auth_hash = self._create_admin_auth_token(auth_key)
        if self.zkobj.auth_hash == auth_hash:
            headers = remember(request, 'admin')
            return Response(headers=headers)
        else:
            raise NotImplementedError()

    @log
    def logout(self, context, request):
        """
        Logs the admin user out.
        """
        headers = forget(request)
        return Response(headers=headers)

    @log
    @connected
    @authorized()
    def set_auth_key(self, context, request):
        """
        Updates the auth key in the system.
        """
        if request.method == "POST":
            auth_key = json.loads(request.body)['auth_key']
            logging.info("Updating API Key.")
            self.zkobj.auth_hash = self._create_admin_auth_token(auth_key)
            return Response()
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def handle_domain_action(self, context, request):
        """
        Updates the domain in the system.
        NOTE: No longer supported. This stub is provided for the
              v1.0 API and will return the empty domain.
        """
        if request.method == "GET":
            return Response(body=json.dumps({'domain':None}))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def handle_url_action(self, context, request):
        if request.method == "GET":
            return Response(body=json.dumps({'url': self.zkobj.url().get()}))
        elif request.method == "POST":
            self.zkobj.url().set(json.loads(request.body).get('url'))
            return Response()
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def handle_info_action(self, context, request):
        if request.method == "GET":
            active = self.zkobj.managers().active_count()
            endpoint_states = self.zkobj.endpoints().state_counts()
            instances = len(self.zkobj.endpoint_ips().list())
            managers = len(self.zkobj.managers().list_active())
            return Response(body=json.dumps({
                'active': active,
                'instances': instances,
                'managers': managers,
                'endpoints': endpoint_states,
            }))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def handle_manager_config_action(self, context, request):
        """
        This handles an action on a manager configuration:
        GET - Returns the manager config in the Response body.
        POST/PUT - Updates the manager with a new config in the request body.
        DELETE - Removes the management config.
        """
        manager = request.matchdict['manager']

        if request.method == "GET":
            # Read the config if available.
            config = self.zkobj.managers().get_config(manager)
            if config is None:
                return Response(status=404, body=manager)
            return Response(body=json.dumps(config))

        elif request.method == "POST" or request.method == "PUT":
            try:
                manager_config = fromstr(request.body)
            except (ConfigParser.Error, TypeError, ValueError):
                return Response(status=403)

            config = ManagerConfig(values=manager_config)
            errors = config.validate()
            if errors:
                return Response(status=400, body=json.dumps(errors))
            else:
                self.zkobj.managers().set_config(manager, manager_config)
                return Response()

        elif request.method == "DELETE":
            self.zkobj.managers().remove_config(manager)
            return Response()
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def list_manager_configs(self, context, request):
        """
        Returns a list of managers configurations.
        """
        if request.method == 'GET':
            configured = self.zkobj.managers().list_configs()
            return Response(body=json.dumps(configured))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def handle_manager_active_action(self, context, request):
        """
        This handles an active manager action:
        GET - Returns the manager info in the Response body.
        """
        manager = request.matchdict['manager']

        if request.method == "GET":
            # Read the config if available.
            info = self.zkobj.managers().info(manager)
            return Response(body=json.dumps(info))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def list_managers_active(self, context, request):
        """
        Returns a list of managers active.
        """
        if request.method == 'GET':
            active = self.zkobj.managers().list_active()
            return Response(body=json.dumps(active))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def handle_manager_log(self, context, request):
        """
        Returns the manager's log.
        """
        manager = request.matchdict['manager']
        since = request.params.get('since', None)
        if since is not None:
            try:
                since = float(since)
            except ValueError:
                since = None

        if request.method == "GET":
            manager_log = ManagerLog(
                self.zkobj.managers().log(manager))
            return Response(body=json.dumps(manager_log.get(since=since)))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def handle_endpoint_action(self, context, request):
        """
        This handles a general endpoint action:
        GET - Returns the endpoint config in the Response body.
        POST/PUT - Manages or updates the endpoint with a new config.
        DELETE - Unmanages the endpoint.
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            return Response(body=json.dumps(endpoint.get_config()))

        elif request.method == "POST" or request.method == "PUT":
            try:
                endpoint_config = fromstr(request.body)
            except (ConfigParser.Error, TypeError, ValueError):
                return Response(status=403)

            config = EndpointConfig(values=endpoint_config)
            errors = config.validate()
            if errors:
                return Response(status=400, body=json.dumps(errors))
            else:
                if request.method == "PUT":
                    # Throw an exception if it exists already.
                    self.zkobj.endpoints().create(endpoint_name, endpoint_config)
                elif request.method == "POST":
                    # Throw an exception if it does not exist.
                    self.zkobj.endpoints().update(endpoint_name, endpoint_config)
                return Response()

        elif request.method == "DELETE":
            self.zkobj.endpoints().remove(endpoint_name)
            return Response()

        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def handle_alias_action(self, context, request):
        """
        This handles a general endpoint action:
        POST/PUT - Post the new endpoint name.
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "POST" or request.method == "PUT":
            new_name = json.loads(request.body)
            self.zkobj.endpoints().alias(endpoint_name, new_name)
            return Response()
        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def handle_state_action(self, context, request):
        """
        This handles a endpoint info request:
        GET - Returns the current endpoint info.
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            state = endpoint.state().current()
            active = endpoint.active
            manager = endpoint.manager
            value = {
                'state': state,
                'active': active or [],
                'manager': manager or None,
            }
            return Response(body=json.dumps(value))

        elif request.method == "POST" or request.method == "PUT":
            state_action = json.loads(request.body)
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            endpoint.state().action(state_action.get('action'))
            return Response()

        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def handle_metric_action(self, context, request):
        """
        This handles a general metric action:
        GET - Get the metric info.
        POST/PUT - Updates the metric info.
        """
        endpoint_name = request.matchdict['endpoint_name']
        endpoint_ip = request.matchdict.get('endpoint_ip', None)

        if request.method == "GET":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            return Response(body=json.dumps(endpoint.metrics or {}))

        elif request.method == "POST" or request.method == "PUT":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            metrics = json.loads(request.body)
            if endpoint_ip is not None:
                ip_metrics = endpoint.ip_metrics()
                ip_metrics.add(endpoint_ip, metrics)
            else:
                endpoint.custom_metrics = metrics
            return Response()

        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def list_endpoint_ips(self, context, request):
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            return Response(body=json.dumps(endpoint.confirmed_ips().list()))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def list_endpoints(self, context, request):
        """
        Returns a list of endpoints currently being managed.
        """
        if request.method == "GET":
            endpoints = self.zkobj.endpoints().list()
            return Response(body=json.dumps(endpoints))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def register_ip_address(self, context, request):
        """
        Publish a new IP explicitly.
        """
        if request.method == "POST" or request.method == "PUT":
            ip_address = request.matchdict.get('endpoint_ip', None)
            if ip_address is not None:
                self.zkobj.new_ips().add(ip_address)
            return Response()
        else:
            return Response(status=403)

    @log
    @connected
    def register_ip_implicit(self, context, request):
        """
        Publish a new IP from an instance.

        NOTE: This does not require authorization.
        Since we don't have this IP registered yet,
        it won't belong to any particular endpoint.
        We therefore allow posting from any IP, and
        will let the managers sort it out.
        """
        if request.method == "POST" or request.method == "PUT":
            ip_address = self._extract_remote_ip(context, request)
            self.zkobj.new_ips().add(ip_address)
            return Response()
        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def unregister_ip_address(self, context, request):
        """
        Unregister the given IP.
        """
        if request.method == "POST" or request.method == "PUT":
            ip_address = request.matchdict.get('endpoint_ip', None)
            if ip_address is not None:
                self.zkobj.drop_ips().add(ip_address)
            return Response()
        else:
            return Response(status=403)

    @log
    @connected
    def unregister_ip_implicit(self, context, request):
        """
        Unregister the given IP.

        See NOTE above in register_ip_implicit().
        """
        if request.method == "POST" or request.method == "PUT":
            ip_address = self._extract_remote_ip(context, request)
            self.zkobj.drop_ips().add(ip_address)
            return Response()
        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def handle_log_action(self, context, request):
        """
        Returns the endpoints' log.
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "POST" or request.method == "PUT":
            level = request.params.get('level', None)
            message = str(json.loads(request.body))
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            endpoint_log = EndpointLog(endpoint.log())
            endpoint_log.post(message, level=level)
            return Response()

        elif request.method == "GET":
            since = request.params.get('since', None)
            if since is not None:
                try:
                    since = float(since)
                except ValueError:
                    since = None
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            endpoint_log = EndpointLog(endpoint.log())
            return Response(body=json.dumps(endpoint_log.get(since=since)))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def list_instances(self, context, request):
        """
        Return a state map for endpoint instances.
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            return Response(body=json.dumps(endpoint.instance_map()))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def handle_instance_action(self, context, request):
        """
        Associate or disassociate an instance.
        """
        endpoint_name = request.matchdict['endpoint_name']
        instance_id = request.matchdict['instance_id']

        if request.method == "POST" or request.method == "PUT":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            endpoint.associate(instance_id)
            return Response()

        elif request.method == "DELETE":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            endpoint.disassociate(instance_id)
            return Response()
        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def list_metadata(self, context, request):
        """
        Return a list of all metadata.
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            return Response(body=json.dumps(endpoint.metadata().list()))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def handle_metadata_action(self, context, request):
        """
        Get, set or delete endpoint metadata.
        """
        endpoint_name = request.matchdict['endpoint_name']
        key_name = request.matchdict['key_name']

        if request.method == "GET":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            data = endpoint.metadata().get(key_name)
            return Response(body=json.dumps(data))

        elif request.method == "POST" or request.method == "PUT":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            endpoint.metadata().add(key_name, json.loads(request.body))
            return Response()

        elif request.method == "DELETE":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            endpoint.metadata().remove(key_name)
            return Response()
        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def list_sessions(self, context, request):
        """
        Returns the endpoints' session list.
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            return Response(body=json.dumps(endpoint.sessions().active_map()))
        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def handle_session_action(self, context, request):
        """
        Returns the endpoints' session list, or drops a session
        """
        endpoint_name = request.matchdict['endpoint_name']
        session = request.matchdict['session']

        if request.method == "GET":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            return Response(body=json.dumps(endpoint.sessions().backend(session)))

        elif request.method == "DELETE":
            endpoint, _ = self.zkobj.endpoints().get(endpoint_name)
            endpoint.sessions().drop(session)
            return Response()
        else:
            return Response(status=403)

HELP = ("""Usage: reactor-api [options]

    Run the API server.

""",)

HOST = cli.OptionSpec(
    "host",
    "The host to bind to.",
    str,
    defaults.DEFAULT_BIND
)

PORT = cli.OptionSpec(
    "port",
    "The port to bind to.",
    int,
    defaults.DEFAULT_PORT
)

def api_main(zk_servers, options):
    api = ReactorApi(zk_servers)
    app = api.get_wsgi_app()
    httpserver.serve(app, host=options.get("host"), port=options.get("port"))

def main():
    server.main(api_main, [HOST, PORT], HELP)

if __name__ == "__main__":
    main()
