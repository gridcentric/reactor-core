import hashlib
import json
import logging
import traceback

from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.security import authenticated_userid
from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy

from . manager import ManagerConfig
from . endpoint import EndpointConfig
from . endpoint import EndpointLog
from . endpoint import State
from . objects.root import Reactor
from . zookeeper.connection import ZookeeperException
from . zookeeper.client import ZookeeperClient

def authorized_admin_only(request_handler=None, forbidden_view=None):
    """
    A Decorator that does a simple check to see if the request is
    authorized before executing the actual handler. NOTE: This will
    only authorize for admins only. 

    Use of this decorator implies use of the @connected decorator.
    """
    def _authorized_admin_only(request_handler):
        def fn(self, context, request):
            try:
                if self._authorize_admin_access(context, request):
                    return request_handler(self, context, request)

                # Access denied
                if forbidden_view:
                    return eval(forbidden_view)(context, request)
                else:
                    # Return an unauthorized response.
                    return Response(status=401, body="unauthorized")
            except:
                # Return an internal error.
                logging.error("Unexpected error: %s" % traceback.format_exc())
                return Response(status=500, body="internal error")

        return fn

    # This decorator can be invoked either with arguments (e.g.
    # @authorized_admin_only(forbidden_view='my_view') or without
    # (e.g. @authorized_admin_only() or @authorized_admin_only).
    #
    # When invoked with (), we must generate a decorator, which
    # python will then apply to the function via '@'. When
    # invoked without (), we skip the generation step and
    # decorate the function. We know how we were invoked via the
    # request_handler parameter - if being called as a function,
    # it will be None; if being called as a decorator, it will
    # be the function being decorated.
    if request_handler:
        # Decorator
        return _authorized_admin_only(request_handler)
    else:
        # Generator
        return _authorized_admin_only

def authorized(request_handler):
    """
    A Decorator that does a simple check to see if the request is
    authorized before executing the actual handler. 

    Use of this decorator implies use of the @connected decorator.
    """
    def fn(self, context, request):
        try:
            if self._authorize_ip_access(context, request) or \
                self._authorize_endpoint_access(context, request) or \
                self._authorize_admin_access(context, request):
                return request_handler(self, context, request)
            else:
                # Return an unauthorized response.
                return Response(status=401, body="unauthorized")
        except:
            # Return an internal error.
            logging.error("Unexpected error: %s" % traceback.format_exc())
            return Response(status=500, body="internal error")

    return fn

def connected(request_handler):
    """
    A decorator that ensures we are connected to the Zookeeper server.
    """
    def try_once(*args, **kwargs):
        self = args[0]
        try:
            self.connect()
            return request_handler(*args, **kwargs)
        except ZookeeperException:
            # Disconnect (next request will reconnect).
            logging.error("Unexpected error: %s" % traceback.format_exc())
            self.disconnect()
            return None
    def fn(*args, **kwargs):
        response = try_once(*args, **kwargs)
        if not(response):
            response = try_once(*args, **kwargs)
        if not(response):
            return Response(status=500, body="internal error")
        else:
            return response
    return fn

class ReactorApi(object):

    AUTH_SALT = 'gridcentricreactor'

    def __init__(self, zk_servers):
        self.client = ReactorClient(zk_servers)
        self.config = Configurator()

        # Set up auth-ticket authentication.
        self.config.set_authentication_policy(
            AuthTktAuthenticationPolicy(
                self.AUTH_SALT))
        self.config.set_authorization_policy(
            ACLAuthorizationPolicy())

        # Setup basic version route.
        self.config.add_route('version', '/')
        self.config.add_view(self.version, route_name='version')

        self._add('auth-key', ['1.0', '1.1'],
                  'auth_key', self.set_auth_key)

        self._add('domain-action', ['1.0'],
                  'domain', self.handle_domain_action)

        self._add('url', ['1.1'],
                  'url', self.handle_url_action)

        self._add('register-implicit', ['1.0', '1.1'],
                  'register', self.register_ip_implicit)

        self._add('register', ['1.0', '1.1'],
                  'register/{endpoint_ip}', self.register_ip_address)

        self._add('unregister-implicit',  ['1.0', '1.1'],
                  'unregister', self.unregister_ip_address)

        self._add('unregister',  ['1.0', '1.1'],
                  'unregister/{endpoint_ip}', self.unregister_ip_address)

        self._add('manager-action',  ['1.0', '1.1'],
                  'managers/{manager}', self.handle_manager_action)

        self._add('manager-list',  ['1.0', '1.1'],
                  'managers', self.list_managers)

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
            self.config.add_view(fn, route_name=route_name)

    def disconnect(self):
        self.client._disconnect()

    def connect(self):
        self.client._connect()

    def get_wsgi_app(self):
        return self.config.make_wsgi_app()

    def _authorize_admin_access(self, context, request):
        auth_hash = self.client.auth_hash()
        if auth_hash != None:
            return authenticated_userid(request) != None
        else:
            # If there is no auth hash then authentication has not been turned
            # on so all requests are allowed by default.
            return True

    def _req_get_auth_key(self, request):
        return request.headers.get('X-Auth-Key', None) or \
               request.params.get('auth_key', None)

    def _authorize_endpoint_access(self, context, request):
        # Pull an endpoint name if it is specified.
        endpoint_name = request.matchdict.get('endpoint_name', None)

        # Pull an endpoint name via the endpoint IP.
        if endpoint_name == None:
            endpoint_ip = request.matchdict.get('endpoint_ip', None)
            if endpoint_ip != None:
                endpoint_name = self.client.ip_address_endpoint(endpoint_ip)

        if endpoint_name != None:
            config = self.client.endpoint_config(endpoint_name)
            if not(config):
                return False

            endpoint_config = EndpointConfig(values=config)
            auth_hash, auth_salt, auth_algo = \
                endpoint_config._get_endpoint_auth()

            if auth_hash != None and auth_hash != "":
                auth_key = self._req_get_auth_key(request)
                if auth_key != None:
                    auth_token = self._create_endpoint_auth_token(\
                        auth_key, auth_salt, auth_algo)
                    return auth_hash == auth_token
                else:
                    return False
            else:
                # If there is not auth hash then authentication has not been
                # turned on so all requests are denied by default.
                return False

    def _extract_remote_ip(self, context, request):
        # TODO(dscannell): The remote ip address is taken from the
        # request.environ['REMOTE_ADDR']. This value may need to be added by
        # some WSGI middleware depending on what webserver fronts this app.
        ip_address = request.environ.get('REMOTE_ADDR', "")
        forwarded_for = request.headers.get('X-Forwarded-For', "")

        # We may be running the API behind scale managers. We don't want to
        # necessarily trust the X-Forwarded-For header that the client passes,
        # but if we've been forwarded from an active manager then we can assume
        # that this header has been placed by a trusted middleman.
        if forwarded_for and \
            (ip_address == "127.0.0.1" or \
             ip_address in self.client.managers_active(full=False)):
            ip_address = forwarded_for

        return ip_address

    def _authorize_ip_access(self, context, request):
        matched_route = request.matched_route
        if matched_route != None:
            if matched_route.name.endswith("-implicit"):
                # We can only do ip authorizing on implicit routes. Essentially
                # we will update the request to confine it to the endpoint with
                # this address.
                request_ip = self._extract_remote_ip(context, request)
                endpoint_name = self.client.ip_address_endpoint(request_ip)
                if endpoint_name != None:
                    # Authorize this request and set the endpoint_name.
                    request.matchdict['endpoint_name'] = endpoint_name
                    request.matchdict['endpoint_ip'] = request_ip
                    return True
                else:
                    raise Exception("Must query from endpoint ip.")

        return False

    def _create_admin_auth_token(self, auth_key):
        if auth_key:
            # NOTE: We use a fixed salt and force sha1 for the admin token.
            # This fixed salt matches the authentication policy used above.
            hash_fn = hashlib.new('sha1')
            hash_fn.update("%s%s" % (self.AUTH_SALT, auth_key))
            return hash_fn.hexdigest()
        else:
            return None

    def check_admin_auth_key(self, auth_key):
        auth_hash = self.client.auth_hash()
        client_hash = self._create_admin_auth_token(auth_key)
        return auth_hash == client_hash

    def _create_endpoint_auth_token(self, auth_key, auth_salt, algo):
        if auth_salt == None:
            auth_salt = ""
        salted = "%s%s" % (auth_salt, auth_key)
        if not algo:
            return salted
        else:
            try:
                hash = hashlib.new(algo, salted)
                return hash.hexdigest()
            except:
                logging.warn("Failed to authenticate against endpoint %s "
                             "because algorithm type is not supported.")
                return ""

    @connected
    def version(self, context, request):
        """
        Get the version implemented by this API.
        """
        if request.method == "GET":
            return Response(body=json.dumps({'version': '1.1'}))
        else:
            return Response(status=403)

    @connected
    @authorized_admin_only
    def set_auth_key(self, context, request):
        """
        Updates the auth key in the system.
        """
        if request.method == "POST" or request.method == "PUT":
            auth_key = json.loads(request.body)['auth_key']
            logging.info("Updating API Key.")
            self.client.auth_hash_set(self._create_admin_auth_token(auth_key))
            return Response()
        else:
            return Response(status=403)

    @connected
    @authorized_admin_only
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

    @connected
    @authorized_admin_only
    def handle_url_action(self, context, request):
        if request.method == "GET":
            url = self.client.url()
            return Response(body=json.dumps({'url': url}))
        elif request.method == "POST":
            url = json.loads(request.body).get('url', '')
            self.client.url_set(url)
            return Response()
        else:
            return Response(status=403)

    @connected
    @authorized_admin_only
    def handle_manager_action(self, context, request):
        """
        This Handles a general manager action:
        GET - Returns the manager config in the Response body
        POST/PUT - Updates the manager with a new config in the request body
        DELETE - Removes the management config.
        """
        manager = request.matchdict['manager']

        if request.method == "GET":
            logging.info("Retrieving manager %s configuration" % manager)
            config = self.client.manager_config(manager)
            if config != None:
                config['uuid'] = self.client.manager_key(manager)
                return Response(body=json.dumps(config))
            else:
                return Response(status=404, body="%s not found" % manager)

        elif request.method == "POST" or request.method == "PUT":
            manager_config = json.loads(request.body)
            logging.info("Updating manager %s" % manager)

            config = ManagerConfig(values=manager_config)
            config._validate()
            errs = config._validate_errors()
            if errs:
                return Response(status=400, body=json.dumps(errs))
            else:
                self.client.manager_update(manager, manager_config)
                return Response()

        elif request.method == "DELETE":
            config = self.client.manager_config(manager)
            if config != None:
                self.client.manager_reset(manager)
                return Response()
            else:
                return Response(status=404, body="%s not found" % manager)

        else:
            return Response(status=403)

    @connected
    @authorized_admin_only
    def list_managers(self, context, request):
        """
        Returns a list of managers currently running.
        """
        if request.method == 'GET':
            configured = self.client.managers_list()
            active = self.client.managers_active(full=True)
            return Response(body=json.dumps(\
                {'configured': configured, 'active': active}))
        else:
            return Response(status=403)

    @connected
    @authorized_admin_only
    def handle_endpoint_action(self, context, request):
        """
        This handles a general endpoint action:
        GET - Returns the endpoint config in the Response body
        POST/PUT - Either manages or updates the endpoint with a new config in the request body
        DELETE - Unmanages the endpoint.
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            logging.info("Retrieving endpoint %s configuration" % endpoint_name)
            config = self.client.endpoint_config(endpoint_name)
            if config != None:
                return Response(body=json.dumps(config))
            else:
                return Response(status=404, body="%s not found" % endpoint_name)

        elif request.method == "DELETE":
            logging.info("Unmanaging endpoint %s" % (endpoint_name))
            self.client.endpoint_unmanage(endpoint_name)
            return Response()

        elif request.method == "POST" or request.method == "PUT":
            endpoint_config = json.loads(request.body)
            logging.info("Managing or updating endpoint %s" % endpoint_name)

            config = EndpointConfig(values=endpoint_config)
            config._validate()
            errs = config._validate_errors()
            if errs:
                return Response(status=400, body=json.dumps(errs))
            else:
                self.client.endpoint_update(endpoint_name, endpoint_config)
                return Response()

        else:
            # Return an unauthorized response.
            return Response(status=401, body="unauthorized")

    @connected
    @authorized
    def handle_state_action(self, context, request):
        """
        This handles a endpoint info request:
        GET - Returns the current endpoint info
        """
        endpoint_name = request.matchdict['endpoint_name']
        endpoint_ip = request.matchdict.get('endpoint_ip', None)

        if request.method == "GET":
            logging.info("Retrieving state for endpoint %s" % endpoint_name)
            config = self.client.endpoint_config(endpoint_name)

            if config != None:
                state = self.client.endpoint_state(endpoint_name) or State.default
                active = self.client.endpoint_active(endpoint_name)
                manager = self.client.endpoint_manager(endpoint_name)

                value = {
                    'state': state,
                    'active': active or [],
                    'manager': manager or None,
                }
                return Response(body=json.dumps(value))
            else:
                return Response(status=404, body="%s not found" % endpoint_name)

        elif request.method == "POST" or request.method == "PUT":
            logging.info("Posting state for endpoint %s" % endpoint_name)
            state_action = json.loads(request.body)
            config = self.client.endpoint_config(endpoint_name)

            if config != None:
                current_state = self.client.endpoint_state(endpoint_name)
                new_state = State.from_action(current_state, state_action.get('action', ''))
                self.client.endpoint_state_set(endpoint_name, new_state)
                return Response()
            else:
                return Response(status=404, body="%s not found" % endpoint_name)

        else:
            return Response(status=403)

    @connected
    @authorized
    def handle_metric_action(self, context, request):
        """
        This handles a general metric action:
        GET - Get the metric info.
        POST/PUT - Updates the metric info.
        """
        endpoint_name = request.matchdict['endpoint_name']
        endpoint_ip = request.matchdict.get('endpoint_ip', None)

        if request.method == "GET":
            logging.info("Retrieving metrics for endpoint %s" % endpoint_name)
            metrics = self.client.endpoint_metrics(endpoint_name)
            return Response(body=json.dumps(metrics or {}))

        elif request.method == "POST" or request.method == "PUT":
            metrics = json.loads(request.body)
            logging.info("Updating metrics for endpoint %s" % endpoint_name)
            self.client.endpoint_metrics_set(endpoint_name, metrics, endpoint_ip)
            return Response()

        else:
            return Response(status=403)

    @connected
    @authorized
    def list_endpoint_ips(self, context, request):
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            return Response(body=json.dumps(\
                {'ip_addresses': self.client.endpoint_ip_addresses(endpoint_name)}))
        else:
            return Response(status=403)

    @connected
    @authorized_admin_only
    def list_endpoints(self, context, request):
        """
        Returns a list of endpoints currently being managed.
        """
        if request.method == "GET":
            endpoints = self.client.endpoint_list()
            return Response(body=json.dumps({'endpoints':endpoints}))
        else:
            return Response(status=403)

    @connected
    @authorized_admin_only
    def register_ip_address(self, context, request):
        """
        Publish a new IP explicitly.
        """
        if request.method == "POST" or request.method == "PUT":
            ip_address = request.matchdict.get('endpoint_ip', None)
            if ip_address:
                logging.info("New IP address %s has been recieved." % (ip_address))
                self.client.ip_address_record(ip_address)
            return Response()
        else:
            return Response(status=403)

    @connected
    def register_ip_implicit(self, context, request):
        """
        Publish a new IP from an instance.
        """
        if request.method == "POST" or request.method == "PUT":
            ip_address = self._extract_remote_ip(context, request)
            logging.info("New IP address %s has been recieved." % (ip_address))
            self.client.ip_address_record(ip_address)
            return Response()
        else:
            return Response(status=403)

    @connected
    @authorized
    def unregister_ip_address(self, context, request):
        """
        Publish a new IP from an instance.
        """
        if request.method == "POST" or request.method == "PUT":
            ip_address = request.matchdict.get('endpoint_ip', None)
            if ip_address:
                logging.info("Unregister requested for IP address %s." % (ip_address))
                self.client.ip_address_drop(ip_address)
            return Response()
        else:
            return Response(status=403)

    @connected
    @authorized_admin_only
    def handle_log_action(self, context, request):
        """
        Returns the endpoints' log.
        """
        endpoint_name = request.matchdict['endpoint_name']
        since = request.params.get('since', None)
        if since:
            try:
                since = float(since)
            except:
                since = None

        if request.method == "GET":
            log = EndpointLog(
                    retrieve_cb=lambda: self.client.endpoint_log_load(endpoint_name))
            return Response(body=json.dumps(log.get(since=since)))
        else:
            return Response(status=403)

    @connected
    @authorized_admin_only
    def list_sessions(self, context, request):
        """
        Returns the endpoints' session list.
        """
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            sessions = {}
            for session in self.client.session_list(endpoint_name):
                sessions[session] = self.client.session_backend(endpoint_name, session)
            return Response(body=json.dumps(sessions))
        else:
            return Response(status=403)

    @connected
    @authorized_admin_only
    def handle_session_action(self, context, request):
        """
        Returns the endpoints' session list, or drops a session
        """
        endpoint_name = request.matchdict['endpoint_name']
        session = request.matchdict['session']

        if request.method == "GET":
            sessions = self.client.session_backend(endpoint_name, session)
            return Response(body=json.dumps({'sessions': sessions}))
        elif request.method == "DELETE":
            config = self.client.endpoint_config(endpoint_name)
            if config != None:
                self.client.session_drop(endpoint_name, session)
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
    definition to support the combination.
    """

    def __init__(self, api):
        self.api = api

        # Bind all base attributes from the API class.
        # After this point, you can freely add new stuff.
        for attr in dir(api):
            if not attr.startswith('__') and not hasattr(self, attr):
                setattr(self, attr, getattr(api, attr))
