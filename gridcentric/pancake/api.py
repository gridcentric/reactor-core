#!/usr/bin/env python

import hashlib
import httplib2
import json
import logging

from pyramid.config import Configurator
from pyramid.response import Response

from gridcentric.pancake.config import ServiceConfig
from gridcentric.pancake.client import PancakeClient

class PancakeApiClient(httplib2.Http):
    """
    A simple client that interacts with the REST interface of the pancakeApi. This is to be
    used in third-party applications that want python bindings to interact with the system.
    """

    def __init__(self, api_url, api_key=None):
        super(PancakeApiClient, self).__init__()
        
        self.api_url = api_url
        self.api_key = api_key
        # Needed to httplib2
        self.force_exception_to_status_code = True

    def list_managed_services(self):
        """
        Returns a list of all the services currently being managed by the pancake.
        """
        resp, body = self._authenticated_request('/gridcentric/pancake/services', 'GET')
        return body.get('services',[])
    
    def manage_service(self, service_name, config):
        """
        Manage the service using the given configuration.
        """
        self._authenticated_request('/gridcentric/pancake/services/%s' %(service_name), 
                                    'POST',
                                    body={'config':config})

    def unmanage_service(self, service_name):
        """
        Unmanage the service.
        """
        self._authenticated_request('/gridcentric/pancake/services/%s' %(service_name), 'DELETE')

    def update_service(self, service_name, config):
        """
        Update the managed service with given configuration values. Note that the config
        can be partial and only those values will be updated.
        """
        self._authenticated_request('/gridcentric/pancake/services/%s' %(service_name), 'POST',
                                    body={'config':config})
    
    def get_service_config(self, service_name):
        """
        Return the service's configuration.
        """
        resp, body = self._authenticated_request('/gridcentric/pancake/services/%s' %
                                                 service_name, 'GET')
        return body.get('config',"")

    def list_service_ips(self, service_name):
        """
        Returns a list of the ip addresses (both dynamically confirmed and manually configured) for
        this service.
        """
        resp, body = self._authenticated_request('/gridcentric/pancake/service/%s/ips' %
                                                 service_name, 'GET')
        return body.get('ip_addresses',[])

    def update_api_key(self, api_key):
        """
        Changes the API key in the system.
        """
        self._authenticated_request('/gridcentric/pancake/auth_key',
                                    'POST', body={'auth_key':api_key})

    def _authenticated_request(self, url, method, **kwargs):
        if self.api_key != None:
            kwargs.setdefault('headers', {})['X-Auth-Key'] = self.api_key
        resp, body = self.request(self.api_url + url, method, **kwargs)
        if resp.status != 200:
            raise Exception(body)
        return resp, body

    def request(self, *args, **kwargs):
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        if 'body' in kwargs:
            kwargs['headers']['Content-Type'] = 'application/json'
            kwargs['body'] = json.dumps(kwargs['body'])

        resp, body = super(PancakeApiClient, self).request(*args, **kwargs)

        if resp.status in (401,):
            raise Exception("Permission denied.")
        if body:
            try:
                body = json.loads(body)
            except ValueError, e:
                pass
        return resp, body

class PancakeApi:

    def __init__(self, zk_servers):
        self.zk_servers = zk_servers
        self.client = None
        self.config = Configurator()

        self.config.add_route('auth-key', '/gridcentric/pancake/auth_key')
        self.config.add_view(self.set_auth_key, route_name='auth-key')

        self.config.add_route('new-ip', '/gridcentric/pancake/new-ip/{ipaddress}')
        self.config.add_view(self.new_ip_address, route_name='new-ip')

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

    def _authorize_admin_access(self, context, request, auth_key):
        self.ensure_connected()
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

    def _authorize_service_access(self, context, request, auth_key):
        self.ensure_connected()
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

    def _authorize_ip_access(self, context, request):
        # TODO(dscannell): The remote ip address is taken from the request.environ['REMOTE_ADDR']. 
        # This value may need to be added by some WSGI middleware depending on what webserver
        # is fronting this app.
        
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
        
        salted = "%s%s" %(auth_salt, auth_key)
        
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

        
    @authorized
    def set_auth_key(self, context, request):
        """
        Updates the auth key in the system.
        """
        self.ensure_connected()
        if request.method == 'POST':
            auth_key = json.loads(request.body)['auth_key']
            logging.info("Updating API Key.")
            self.client.set_auth_hash(self._create_admin_auth_token(auth_key))

        return Response()

    @authorized
    def handle_service_action(self, context, request):
        """
        This Handles a general service action:
        GET - Returns the service config in the Response body
        POST - Either manages or updates the service with a new config in the request body
        DELETE - Unmanages the service.
        """
        self.ensure_connected()
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

    @authorized
    def list_service_ips(self, context, request):
        self.ensure_connected()
        service_name = request.matchdict['service_name']
        if request.method == 'GET':
            return Response(body=json.dumps(
                        {'ip_addresses': self.client.get_service_ip_addresses(service_name)}))
        return Response()

    @authorized
    def list_services(self, context, request):
        """
        Returns a list of services currently being managed.
        """
        self.ensure_connected()
        services = self.client.list_managed_services()
        return Response(body=json.dumps({'services':services}))

    def new_ip_address(self, context, request):
        self.ensure_connected()
        ip_address = request.matchdict['ipaddress']
        logging.info("New IP address %s has been recieved." % (ip_address))
        self.client.record_new_ipaddress(ip_address)
        return Response()
