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

from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.security import remember, forget, authenticated_userid
from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy

from . import utils
from . import ips as ips_mod
from . log import log
from . config import fromstr
from . manager import ManagerConfig
from . manager import ManagerLog
from . endpoint import EndpointConfig
from . endpoint import EndpointLog
from . objects.root import Reactor
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
                return request_handler(self, context, request, **kwargss)

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

class ReactorApi(object):

    AUTH_SALT = 'gridcentricreactor'

    def __init__(self, zk_servers):
        super(ReactorApi, self).__init__()
        self.client = ZookeeperClient(zk_servers)
        self.zkobj = Reactor(self.client)
        self.config = Configurator()

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

        self._add('manager-action',  ['1.0', '1.1'],
                  'managers/{manager}', self.handle_manager_action)

        self._add('manager-list',  ['1.0', '1.1'],
                  'managers', self.list_managers)

        self._add('manager-log', ['1.1'],
                  'managers/{manager}/log', self.handle_manager_log)

        self._add('endpoint-action',  ['1.0', '1.1'],
                  'endpoints/{endpoint_name}', self.handle_endpoint_action)

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
            # If there is no auth hash then authentication has not been turned
            # on so all requests are allowed by default.
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
                endpoint_name = self.zkobj.endpoint_ips().get(endpoint_ip)

        if endpoint_name is None:
            return False

        # Load the endpoint config.
        config = self.zkobj.endpoints().get(endpoint_name).get_config()
        if config is None:
            return False

        # Parse authentication details.
        endpoint_config = EndpointConfig(values=config)
        auth_hash, auth_salt, auth_algo = \
            endpoint_config.endpoint_auth()

        if auth_hash is not None and auth_hash != "":
            auth_key = self._req_get_auth_key(request)
            if auth_key is not None:
                auth_token = self._create_endpoint_auth_token(\
                    auth_key, auth_salt, auth_algo)
                return (auth_hash == auth_token)

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
            ip_address in self.zkobj.managers().list()):
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
                endpoint_name = self.zkobj.endpoint_ips().get(request_ip)
                if endpoint_name is not None:
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
        if request.method == "POST" or request.method == "PUT":
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
            managers = len(self.zkobj.managers().key_map())
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
    def handle_manager_action(self, context, request):
        """
        This Handles a general manager action:
        GET - Returns the manager config in the Response body
        POST/PUT - Updates the manager with a new config in the request body
        DELETE - Removes the management config.
        """
        manager = request.matchdict['manager']

        if request.method == "GET":
            config = self.zkobj.managers().get_config(manager)
            if config is not None:
                try:
                    config['uuid'] = self.zkobj.managers().key(manager)
                    config['info'] = self.zkobj.managers().info(config['uuid'])
                except:
                    config['uuid'] = None
                    config['info'] = None
                return Response(body=json.dumps(config))
            else:
                return Response(status=404, body="%s not found" % manager)

        elif request.method == "POST" or request.method == "PUT":
            manager_config = fromstr(request.body)
            config = ManagerConfig(values=manager_config)
            errors = config.validate()
            if errors:
                return Response(status=400, body=json.dumps(errors))
            else:
                self.zkobj.managers().set_config(manager, manager_config)
                return Response()

        elif request.method == "DELETE":
            config = self.zkobj.managers().get_config(manager)
            if config is not None:
                # Delete the given manager completely.
                self.zkobj.managers().remove_config(manager)
                return Response()
            else:
                return Response(status=404, body="%s not found" % manager)

        else:
            return Response(status=403)

    @log
    @connected
    @authorized()
    def list_managers(self, context, request):
        """
        Returns a list of managers currently running.
        """
        if request.method == 'GET':
            configured = self.zkobj.managers().list()
            active = self.zkobj.managers().key_map()
            return Response(body=json.dumps(\
                {'configured': configured, 'active': active}))
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
        GET - Returns the endpoint config in the Response body
        POST/PUT - Either manages or updates the endpoint with a new config in the request body
        DELETE - Unmanages the endpoint.
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            config = self.zkobj.endpoints().get(endpoint_name).get_config()
            if config is not None:
                return Response(body=json.dumps(config))
            else:
                return Response(status=404, body="%s not found" % endpoint_name)

        elif request.method == "POST" or request.method == "PUT":
            endpoint_config = fromstr(request.body)
            config = EndpointConfig(values=endpoint_config)
            errors = config.validate()
            if errors:
                return Response(status=400, body=json.dumps(errors))
            else:
                self.zkobj.endpoints().get(endpoint_name).set_config(endpoint_config)
                return Response()

        elif request.method == "DELETE":
            self.zkobj.endpoints().unmanage(endpoint_name)
            return Response()

        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def handle_state_action(self, context, request):
        """
        This handles a endpoint info request:
        GET - Returns the current endpoint info
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            endpoint = self.zkobj.endpoints().get(endpoint_name)
            config = endpoint.get_config()
            if config is not None:
                state = endpoint.state().current()
                active = endpoint.active
                manager = endpoint.manager
                value = {
                    'state': state,
                    'active': active or [],
                    'manager': manager or None,
                }
                return Response(body=json.dumps(value))
            else:
                return Response(status=404, body="%s not found" % endpoint_name)

        elif request.method == "POST" or request.method == "PUT":
            state_action = json.loads(request.body)
            endpoint = self.zkobj.endpoints().get(endpoint_name)
            config = endpoint.get_config()

            if config is not None:
                endpoint.state().action(state_action.get('action'))
                return Response()
            else:
                return Response(status=404, body="%s not found" % endpoint_name)

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
            metrics = self.zkobj.endpoints().get(endpoint_name).metrics
            return Response(body=json.dumps(metrics or {}))

        elif request.method == "POST" or request.method == "PUT":
            metrics = json.loads(request.body)
            if endpoint_ip is not None:
                ip_metrics = self.zkobj.endpoints().get(endpoint_name).ip_metrics()
                ip_metrics.add(endpoint_ip, metrics)
            else:
                self.zkobj.endpoints().get(endpoint_name).custom_metrics = metrics
            return Response()

        else:
            return Response(status=403)

    @log
    @connected
    @authorized(allow_endpoint=True)
    def list_endpoint_ips(self, context, request):
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            ips = self.zkobj.endpoints().get(
                endpoint_name).confirmed_ips().list()
            return Response(body=json.dumps({'ip_addresses': ips}))
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
            return Response(body=json.dumps({'endpoints':endpoints}))
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
        since = request.params.get('since', None)
        if since is not None:
            try:
                since = float(since)
            except ValueError:
                since = None

        if request.method == "GET":
            endpoint_log = EndpointLog(
                self.zkobj.endpoints().get(endpoint_name).log())
            return Response(body=json.dumps(endpoint_log.get(since=since)))
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
            sessions = self.zkobj.endpoints().get(
                endpoint_name).sessions().active_map()
            return Response(body=json.dumps(sessions))
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
            backend = self.zkobj.endpoints().get(endpoint_name).sessions().backend(session)
            return Response(body=json.dumps(backend))

        elif request.method == "DELETE":
            endpoint = self.zkobj.endpoints().get(endpoint_name)
            if endpoint.get_config() is not None:
                endpoint.sessions().drop(session)
            else:
                return Response(status=404, body="%s not found" % endpoint_name)
            return Response()
        else:
            return Response(status=403)

class ReactorApiExtension(object):
    """
    This class can be used to extend a API instance in order to
    provide additional functionality. It works as follows:

    * A class inherits from ReactorApiExtension.
    * You instantiate the class with an API object.
    * You then treat the ReactorApiExtension as the api.

    This was done because we wanted to be able to provide arbitrary
    API extensions (API interface, clustering, etc.) without having
    to specify a strict ordering as they are independent features.

    Sort of like Mixins, but without having to create a new class
    definition to support the combination. Could have gone with more
    explicit Mixins or metaclasses or other craziness, but I prefer
    the manual approach with a little bit more explicitness. There
    are certainly some ugly bits, but at least it all makes sense.
    """

    def __init__(self, api):
        super(ReactorApiExtension, self).__init__()
        self.api = api

        # Bind all base attributes from the API class.
        # After this point, you can freely add new stuff.
        # This allows us to treat this class as the API
        # object. NOTE: all of the original API views have
        # been bound to the original API methods, so you
        # *cannot* just change the methods. This is very
        # much intentional. If you want to override some
        # built-in behavior, then the API should have some
        # internal function that it calls which can be
        # overriden by the extension functionality.
        for attr in dir(api):
            if not attr.startswith('__') and not hasattr(self, attr):
                setattr(self, attr, getattr(api, attr))
