import hashlib
import json
import logging
import traceback

from pyramid.config import Configurator
from pyramid.response import Response

from gridcentric.pancake.endpoint import EndpointConfig
from gridcentric.pancake.endpoint import State
from gridcentric.pancake.manager import ManagerConfig
from gridcentric.pancake.zooclient import PancakeClient
from gridcentric.pancake.zookeeper.connection import ZookeeperException

def get_auth_key(request):
    return request.headers.get('X-Auth-Key', None) or \
           request.params.get('auth_key', None)

def authorized_admin_only(request_handler):
    """
    A Decorator that does a simple check to see if the request is
    authorized before executing the actual handler. NOTE: This will
    only authorize for admins only. 
    """
    def fn(self, context, request):
        auth_key = get_auth_key(request)
        try:
            if self._authorize_admin_access(context, request, auth_key):
                return request_handler(self, context, request)
            else:
                # Return an unauthorized response.
                return Response(status=401, body="unauthorized")
        except:
            # Return an internal error.
            logging.error("Unexpected error: %s" % traceback.format_exc())
            return Response(status=500, body="internal error")

    return fn

def authorized(request_handler):
    """
    A Decorator that does a simple check to see if the request is
    authorized before executing the actual handler. 
    """
    def fn(self, context, request):
        auth_key = get_auth_key(request)
        try:
            if self._authorize_ip_access(context, request) or \
                self._authorize_endpoint_access(context, request, auth_key) or \
                self._authorize_admin_access(context, request, auth_key):
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
            self.ensure_connected()
            return request_handler(*args, **kwargs)
        except ZookeeperException:
            # Disconnect (next request will reconnect).
            self.disconnect()
            return None
    def fn(*args, **kwargs):
        response = try_once(*args, **kwargs)
        if not(response):
            response = try_once(*args, **kwargs)
        return response
    return fn

class PancakeApi:

    def __init__(self, zk_servers):
        self.zk_servers = zk_servers
        self.client = None
        self.config = Configurator()

        self.config.add_route('version', '/')
        self.config.add_view(self.version, route_name='version')

        self.config.add_route('auth-key', '/v1.0/auth_key')
        self.config.add_view(self.set_auth_key, route_name='auth-key')

        self.config.add_route('domain-action', '/v1.0/domain')
        self.config.add_view(self.handle_domain_action, route_name='domain-action')

        self.config.add_route('register', '/v1.0/register')
        self.config.add_view(self.register_ip_address, route_name='register')

        self.config.add_route('manager-action', '/v1.0/managers/{manager}')
        self.config.add_route('manager-action-default', '/v1.0/config')
        self.config.add_view(self.handle_manager_action, route_name='manager-action')
        self.config.add_view(self.handle_manager_action, route_name='manager-action-default')

        self.config.add_route('manager-list', '/v1.0/managers')
        self.config.add_view(self.list_managers, route_name='manager-list')

        self.config.add_route('endpoint-action', '/v1.0/endpoints/{endpoint_name}')
        self.config.add_view(self.handle_endpoint_action, route_name='endpoint-action')

        self.config.add_route('endpoint-list', '/v1.0/endpoints')
        self.config.add_view(self.list_endpoints, route_name='endpoint-list')

        self.config.add_route('endpoint-ip-list',
            '/v1.0/endpoints/{endpoint_name}/ips')
        self.config.add_route('endpoint-ip-list-implicit',
            '/v1.0/endpoint/ips')
        self.config.add_view(self.list_endpoint_ips, route_name='endpoint-ip-list')
        self.config.add_view(self.list_endpoint_ips, route_name='endpoint-ip-list-implicit')

        self.config.add_route('metric-action',
            '/v1.0/endpoints/{endpoint_name}/metrics')
        self.config.add_route('metric-action-implicit',
            '/v1.0/endpoint/metrics')
        self.config.add_view(self.handle_metric_action, route_name='metric-action')
        self.config.add_view(self.handle_metric_action, route_name='metric-action-implicit')

        self.config.add_route('metric-ip-action',
            '/v1.0/endpoints/{endpoint_name}/metrics/{endpoint_ip}')
        self.config.add_route('metric-ip-action-implicit',
            '/v1.0/endpoint/metrics/{endpoint_ip}')
        self.config.add_view(self.handle_metric_action, route_name='metric-ip-action')
        self.config.add_view(self.handle_metric_action, route_name='metric-ip-action-implicit')

        self.config.add_route('endpoint-state-action',
            '/v1.0/endpoints/{endpoint_name}/state')
        self.config.add_route('endpoint-state-action-implicit',
            '/v1.0/endpoint/state')
        self.config.add_view(self.handle_state_action, route_name='endpoint-state-action')
        self.config.add_view(self.handle_state_action, route_name='endpoint-state-action-implicit')

    def reconnect(self, zk_servers):
        self.disconnect()
        self.zk_servers = zk_servers
        self.client = PancakeClient(zk_servers)

    def disconnect(self):
        if self.client:
            self.client.close()
        self.client = None

    def ensure_connected(self):
        if not(self.client):
            self.reconnect(self.zk_servers)

    def get_wsgi_app(self):
        return self.config.make_wsgi_app()

    @connected
    def _authorize_admin_access(self, context, request, auth_key):
        auth_hash = self.client.auth_hash()
        if auth_hash != None:
            if auth_key != None:
                auth_token = self._create_admin_auth_token(auth_key)
                return auth_hash == auth_token
            else:
                return False
        else:
            # If there is no auth hash then authentication has not been turned
            # on so all requests are allowed by default.
            return True

    @connected
    def _authorize_endpoint_access(self, context, request, auth_key):
        endpoint_name = request.matchdict.get('endpoint_name', None)

        if endpoint_name != None:
            config = self.client.get_endpoint_config(endpoint_name)
            if not(config):
                return False

            endpoint_config = EndpointConfig(config)
            auth_hash, auth_salt, auth_algo = \
                endpoint_config.get_endpoint_auth()

            if auth_hash != None and auth_hash != "":
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
        # request.environ['REMOTE_ADDR'].  This value may need to be added by
        # some WSGI middleware depending on what webserver is fronting this
        # app.
        ip_address = request.environ.get('REMOTE_ADDR', "")
        forwarded_for = request.headers.get('X-Forwarded-For', "")

        # We may be running the API behind scale managers. We don't want to
        # necessarily trust the X-Forwarded-For header that the client passes,
        # but if we've been forwarded from an active manager then we can assume
        # that this header has been placed by a trusted middleman.
        if forwarded_for and ip_address in self.client.get_managers_active(full=False):
            ip_address = forwarded_for

        return ip_address

    @connected
    def _authorize_ip_access(self, context, request):
        matched_route = request.matched_route
        if matched_route != None:
            if matched_route.name.endswith("-implicit"):
                # We can only do ip authorizing on implicit routes. Essentially
                # we will update the request to confine it to the endpoint with
                # this address.
                request_ip = self._extract_remote_ip(context, request)
                endpoint_name = self.client.get_ip_address_endpoint(request_ip)
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
            salt = 'gridcentricpancake'
            return hashlib.sha1("%s%s" % (salt, auth_key)).hexdigest()
        else:
            return None

    def _create_endpoint_auth_token(self, auth_key, auth_salt, algo):
        if auth_salt == None:
            auth_salt = ""

        salted = "%s%s" % (auth_salt, auth_key)

        if algo == "none":
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
            response = Response(body=json.dumps({'version':'1.0'}))
        else:
            response = Response(status=403)

        return response

    @connected
    @authorized_admin_only
    def set_auth_key(self, context, request):
        """
        Updates the auth key in the system.
        """
        response = Response()

        if request.method == "POST" or request.method == "PUT":
            auth_key = json.loads(request.body)['auth_key']
            logging.info("Updating API Key.")
            self.client.set_auth_hash(self._create_admin_auth_token(auth_key))

        else:
            response = Response(status=403)

        return response

    @connected
    @authorized_admin_only
    def handle_domain_action(self, context, request):
        """
        Updates the domain in the system.
        """
        response = Response()

        if request.method == "GET":
            logging.info("Retrieving Domain.")
            domain = self.client.domain()
            response = Response(body=json.dumps({'domain':domain}))

        elif request.method == "POST" or request.method == "PUT":
            domain = json.loads(request.body)['domain']
            logging.info("Updating Domain.")
            self.client.set_domain(domain)

        else:
            response = Response(status=403)

        return response

    @connected
    @authorized_admin_only
    def handle_manager_action(self, context, request):
        """
        This Handles a general manager action:
        GET - Returns the manager config in the Response body
        POST/PUT - Updates the manager with a new config in the request body
        DELETE - Removes the management config.
        """
        manager = request.matchdict.get('manager', 'default')
        response = Response()

        if request.method == "GET":
            logging.info("Retrieving manager %s configuration" % manager)

            if not(manager) or manager == "default":
                config = self.client.get_config()
            else:
                config = self.client.get_manager_config(manager)

            if config != None:
                manager_config = ManagerConfig(config)
                response = Response(body=json.dumps({'config' : str(manager_config)}))
            else:
                response = Response(status=404, body="%s not found" % manager)

        elif request.method == "POST" or request.method == "PUT":
            manager_config = json.loads(request.body)
            logging.info("Updating manager %s" % manager)

            if not(manager) or manager == "default":
                self.client.update_config(manager_config.get('config', ""))
            else:
                self.client.update_manager_config(manager, manager_config.get('config', ""))

        elif request.method == "DELETE":
            config = self.client.get_manager_config(manager)
            if config != None:
                self.client.remove_manager_config(manager)
                response = Response()
            else:
                response = Response(status=404, body="%s not found" % manager)

        else:
            response = Response(status=403)

        return response

    @connected
    @authorized_admin_only
    def list_managers(self, context, request):
        """
        Returns a list of managers currently running.
        """

        if request.method == 'GET':
            managers_configured = self.client.list_managers_configured()
            managers_active = self.client.get_managers_active(full=True)
            response = Response(body=json.dumps(\
                        { 'managers_configured' : managers_configured,
                          'managers_active' : managers_active }))
        else:
            response = Response(status=403)

        return response

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
        response = Response()

        if request.method == "GET":
            logging.info("Retrieving endpoint %s configuration" % endpoint_name)
            config = self.client.get_endpoint_config(endpoint_name)

            if config != None:
                endpoint_config = EndpointConfig(self.client.get_endpoint_config(endpoint_name))
                response = Response(body=json.dumps({'config' : str(endpoint_config)}))
            else:
                response = Response(status=404, body="%s not found" % endpoint_name)

        elif request.method == "DELETE":
            logging.info("Unmanaging endpoint %s" % (endpoint_name))
            self.client.unmanage_endpoint(endpoint_name)

        elif request.method == "POST" or request.method == "PUT":
            endpoint_config = json.loads(request.body)
            logging.info("Managing or updating endpoint %s" % endpoint_name)
            self.client.update_endpoint(endpoint_name, endpoint_config.get('config', ''))

        else:
            # Return an unauthorized response.
            return Response(status=401, body="unauthorized")

        return response

    @connected
    @authorized
    def handle_state_action(self, context, request):
        """
        This handles a endpoint info request:
        GET - Returns the current endpoint info
        """
        endpoint_name = request.matchdict['endpoint_name']
        endpoint_ip = request.matchdict.get('endpoint_ip', None)
        response = Response()

        if request.method == "GET":
            logging.info("Retrieving state for endpoint %s" % endpoint_name)
            config = self.client.get_endpoint_config(endpoint_name)

            if config != None:
                state   = self.client.get_endpoint_state(endpoint_name) or State.default
                active  = self.client.get_endpoint_active(endpoint_name)
                manager = self.client.get_endpoint_manager(endpoint_name)

                value = {
                    'state'   : state,
                    'active'  : active or [],
                    'manager' : manager or None,
                }
                response = Response(body=json.dumps(value))
            else:
                response = Response(status=404, body="%s not found" % endpoint_name)

        elif request.method == "POST" or request.method == "PUT":
            logging.info("Posting state for endpoint %s" % endpoint_name)
            state_action = json.loads(request.body)
            config = self.client.get_endpoint_config(endpoint_name)

            if config != None:
                current_state = self.client.get_endpoint_state(endpoint_name)
                new_state = State.from_action(current_state, state_action.get('action', ''))
                self.client.set_endpoint_state(endpoint_name, new_state)
                response = Response()
            else:
                response = Response(status=404, body="%s not found" % endpoint_name)

        else:
            response = Response(status=403)

        return response

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
        response = Response()

        if request.method == "GET":
            logging.info("Retrieving metrics for endpoint %s" % endpoint_name)
            metrics = self.client.get_endpoint_metrics(endpoint_name)
            response = Response(body=json.dumps(metrics or {}))

        elif request.method == "POST" or request.method == "PUT":
            metrics = json.loads(request.body)
            logging.info("Updating metrics for endpoint %s" % endpoint_name)
            self.client.set_endpoint_metrics(endpoint_name, metrics, endpoint_ip)

        else:
            response = Response(status=403)

        return response

    @connected
    @authorized
    def list_endpoint_ips(self, context, request):
        endpoint_name = request.matchdict['endpoint_name']

        if request.method == "GET":
            response = Response(body=json.dumps({'ip_addresses': \
                self.client.get_endpoint_ip_addresses(endpoint_name)}))
        else:
            response = Response(status=403)

        return response

    @connected
    @authorized_admin_only
    def list_endpoints(self, context, request):
        """
        Returns a list of endpoints currently being managed.
        """
        if request.method == "GET":
            endpoints = self.client.list_managed_endpoints()
            response = Response(body=json.dumps({'endpoints':endpoints}))
        else:
            response = Response(status=403)

        return response

    @connected
    def register_ip_address(self, context, request):
        """
        Publish a new IP from an instance.
        """
        if request.method == "POST" or request.method == "PUT":
            ip_address = self._extract_remote_ip(context, request)
            logging.info("New IP address %s has been recieved." % (ip_address))
            self.client.record_new_ipaddress(ip_address)
            response = Response()
        else:
            response = Response(status=403)

        return response
