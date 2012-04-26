#!/usr/bin/env python

import hashlib
import json
import logging

from pyramid.config import Configurator
from pyramid.response import Response

from gridcentric.pancake.config import ServiceConfig
from gridcentric.pancake.zooclient import PancakeClient
from gridcentric.pancake.zookeeper.connection import ZookeeperException

def authorized(request_handler):
    """
    A Decorator that does a simple check to see if the request is
    authorized before executing the actual handler. 
    """
    def fn(self, context, request):
         auth_key = request.headers.get('X-Auth-Key', None)
         if self._authorize_admin_access(context, request, auth_key) or \
            self._authorize_service_access(context, request, auth_key) or \
            self._authorize_ip_access(context, request):
               
            return request_handler(self, context, request)
         else:
            # Return an unauthorized response.
            return Response(status=401)
    return fn

def connected(request_handler):
    """
    A decorator that ensures we are connected to the Zookeeper server.
    """
    def fn(*args, **kwargs):
        try:
            self = args[0]
            self.ensure_connected()
            return request_handler(*args, **kwargs)
        except ZookeeperException:
            # Disconnect (next request will reconnect).
            self.disconnect()
    return fn

class PancakeApi:

    def __init__(self, zk_servers):
        self.zk_servers = zk_servers
        self.client = None
        self.config = Configurator()

        self.config.add_route('auth-key', '/gridcentric/pancake/auth_key')
        self.config.add_view(self.set_auth_key, route_name='auth-key')

        self.config.add_route('new-ip', '/gridcentric/pancake/new-ip/{ipaddress}')
        self.config.add_view(self.new_ip_address, route_name='new-ip')

        self.config.add_route('manager-action', '/gridcentric/pancake/managers/{manager}')
        self.config.add_view(self.handle_manager_action, route_name='manager-action')

        self.config.add_route('manager-list', '/gridcentric/pancake/managers')
        self.config.add_view(self.list_managers, route_name='manager-list')

        self.config.add_route('service-action', '/gridcentric/pancake/services/{service_name}')
        self.config.add_view(self.handle_service_action, route_name='service-action')

        self.config.add_route('service-list', '/gridcentric/pancake/services')
        self.config.add_view(self.list_services, route_name='service-list')

        self.config.add_route('service-ip-list', '/gridcentric/pancake/service/{service_name}/ips')
        self.config.add_route('service-ip-list-implicit', '/gridcentric/pancake/service/ips')
        self.config.add_view(self.list_service_ips, route_name='service-ip-list')
        self.config.add_view(self.list_service_ips, route_name='service-ip-list-implicit')

    def reconnect(self, zk_servers):
        self.client = PancakeClient(zk_servers)

    def disconnect(self):
        self.client = None

    def ensure_connected(self):
        if not(self.client):
            self.reconnect(self.zk_servers)

    def get_wsgi_app(self):
        return self.config.make_wsgi_app()

    def authorized_admin_only(request_handler):
        """
        A Decorator that does a simple check to ensure that the reqyest
        is authorized by the admin only before executing the actual handler.
        """
        def fn(self, context, request):
             
             auth_key = request.headers.get('X-Auth-Key', None)
             if self._authorize_admin_access(context, request, auth_key):
                return request_handler(self, context, request)
             else:
                 # Return an unauthorized response.
                return Response(status=401)
        return fn

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
    def _authorize_service_access(self, context, request, auth_key):
        service_name = request.matchdict.get('service_name', None)
        if service_name != None:
            service_config = ServiceConfig(self.client.get_service_config(service_name))
            auth_hash, auth_salt, auth_algo = service_config.get_service_auth()
            
            if auth_hash != None and auth_hash != "":
                if auth_key != None:
                    auth_token = self._create_service_auth_token(auth_key, auth_salt, auth_algo)
                    return auth_hash == auth_token
                else:
                    return False
            else:
                # If there is not auth hash then authentication has not been turned
                # on so all requests are allowed by default.
                return True

    @connected
    def _authorize_ip_access(self, context, request):
        # TODO(dscannell): The remote ip address is taken from the
        # request.environ['REMOTE_ADDR'].  This value may need to be added by
        # some WSGI middleware depending on what webserver is fronting this
        # app.
        matched_route = request.matched_route
        if matched_route != None:
            if matched_route.name.endswith("-implicit"):
                # We can only do ip authorizing on implicit routes. Essentially
                # we will update the request to confine it to the service with
                # this address.
                request_ip = request.environ.get('REMOTE_ADDR', "")
                service_name = self.client.get_ip_address_service(request_ip)
                if service_name != None:
                    # Authorize this request and set the service_name
                    request.matchdict['service_name'] = service_name
                    return True
        return False

    def _create_admin_auth_token(self, auth_key):
        salt = 'gridcentricpancake'
        return hashlib.sha1("%s%s" %(salt, auth_key)).hexdigest()
    
    def _create_service_auth_token(self, auth_key, auth_salt, algo):
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
                logging.warn("Failed to authenticate against service %s "
                             "because algorithm type is not supported.")
                return ""

    @connected
    @authorized
    def set_auth_key(self, context, request):
        """
        Updates the auth key in the system.
        """
        if request.method == 'POST':
            auth_key = json.loads(request.body)['auth_key']
            logging.info("Updating API Key.")
            self.client.set_auth_hash(self._create_admin_auth_token(auth_key))

        return Response()

    @connected
    @authorized
    def handle_manager_action(self, context, request):
        """
        This Handles a general manager action:
        GET - Returns the manager config in the Response body
        POST - Updates the manager with a new config in the request body
        DELETE - Removes the management config.
        """
        manager = request.matchdict['manager']
        response = Response()
        if request.method == "GET":
            logging.info("Retrieving manager %s configuration" % manager)
            if not(manager) or manager == "default":
                manager_config = self.client.get_config(manager) or ""
            else:
                manager_config = self.client.get_manager_config(manager) or ""
            response = Response(body=json.dumps({'config':manager_config}))
        elif request.method == "POST":
            manager_config = json.loads(request.body)
            logging.info("Updating manager %s" % manager)
            if not(manager) or manager == "default":
                self.client.update_config(manager_config.get('config',""))
            else:
                self.client.update_manager_config(manager, manager_config.get('config',""))
        return response

    @connected
    @authorized
    def list_managers(self, context, request):
        """
        Returns a list of managers currently running.
        """
        managers_configured = self.client.list_managers_configured()
        managers_active = self.client.list_managers_active()
        response = { 'managers_configured':managers_configured,
                     'managers_active':managers_active }
        return Response(body=json.dumps(response))

    @connected
    @authorized
    def handle_service_action(self, context, request):
        """
        This Handles a general service action:
        GET - Returns the service config in the Response body
        POST - Either manages or updates the service with a new config in the request body
        DELETE - Unmanages the service.
        """
        service_name = request.matchdict['service_name']
        response = Response()
        if request.method == "GET":
            logging.info("Retrieving service %s configuration" % service_name)
            service_config = self.client.get_service_config(service_name)
            response = Response(body=json.dumps({'config':service_config}))
        elif request.method == "DELETE":
            logging.info("Unmanaging service %s" %(service_name))
            self.client.unmanage_service(service_name)
        elif request.method == "POST":
            service_config = json.loads(request.body)
            logging.info("Managing or updating service %s" % service_name)
            self.client.update_service(service_name, service_config.get('config',""))
        return response

    @connected
    @authorized
    def list_service_ips(self, context, request):
        service_name = request.matchdict['service_name']
        if request.method == 'GET':
            return Response(body=json.dumps(
                        {'ip_addresses': self.client.get_service_ip_addresses(service_name)}))
        return Response()

    @connected
    @authorized
    def list_services(self, context, request):
        """
        Returns a list of services currently being managed.
        """
        services = self.client.list_managed_services()
        return Response(body=json.dumps({'services':services}))

    @connected
    def new_ip_address(self, context, request):
        ip_address = request.matchdict['ipaddress']
        logging.info("New IP address %s has been recieved." % (ip_address))
        self.client.record_new_ipaddress(ip_address)
        return Response()
