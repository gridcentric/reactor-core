import hashlib
import httplib2
import json
import logging

from pyramid.config import Configurator
from pyramid.response import Response

from gridcentric.scalemanager.client import ScaleManagerClient

class ScaleManagerApiClient(httplib2.Http):
    """
    A simple client that interacts with the REST interface of the ScalemanagerApi. This is to be
    used in third-party applications that want python bindings to interact with the system.
    """
    
    def __init__(self, api_url, api_key=None):
        super(ScaleManagerApiClient, self).__init__()
        
        self.api_url = api_url
        self.api_key = api_key
        # Needed to httplib2
        self.force_exception_to_status_code = True

    def list_managed_services(self):
        """
        Returns a list of all the services currently being managed by the ScaleManager.
        """
        resp, body = self._authenticated_request('/gridcentric/scalemanager/services', 'GET')
        return body.get('services',[])
    
    def manage_service(self, service_name, config):
        """
        Manage the service using the given configuration.
        """
        self._authenticated_request('/gridcentric/scalemanager/services/%s' %(service_name), 
                                    'POST',
                                    body={'config':config})
    
    def unmanage_service(self, service_name):
        """
        Unmanage the service
        """
        self._authenticated_request('/gridcentric/scalemanager/services/%s' %(service_name), 'DELETE')
        
    def update_service(self, service_name, config):
        """
        Update the managed service with given configuration values. Note that the config
        can be partial and only those values will be updated.
        """
        self._authenticated_request('/gridcentric/scalemanager/services/%s' %(service_name), 'POST',
                                    body={'config':config})
    
    def get_service_config(self, service_name):
        """
        Return the service's configuration
        """
        resp, body = self._authenticated_request('/gridcentric/scalemanager/services/%s' %(service_name), 
                                                 'GET')
        return body.get('config',"")

    def update_api_key(self, api_key):
        """
        Changes the API key in the system.
        """
        self._authenticated_request('/gridcentric/scalemanager/auth_key', 'POST', body={'auth_key':api_key})

    def update_agent_stats(self, agent_name, stats):
        """
        Updates the agent stats.
        Stats should be a dictionary of the form { identifier : value }
        """
        self._authenticated_request('/gridcentric/scalemanager/agent/%s' %(agent_name), 'POST', body=stats)

    def _authenticated_request(self, url, method, **kwargs):
        if self.api_key != None:
            kwargs.setdefault('headers', {})['X-Auth-Key'] = self.api_key
        resp, body = self.request(self.api_url + url, method, **kwargs)
        return resp, body

    def request(self, *args, **kwargs):
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        if 'body' in kwargs:
            kwargs['headers']['Content-Type'] = 'application/json'
            kwargs['body'] = json.dumps(kwargs['body'])

        resp, body = super(ScaleManagerApiClient, self).request(*args, **kwargs)

        if resp.status in (401,):
            raise Exception("Permission denied.")
        if body:
            try:
                body = json.loads(body)
            except ValueError, e:
                pass
        return resp, body

class ScaleManagerApi:
    
    def __init__(self, zk_servers):
        self.client = ScaleManagerClient(zk_servers)
        self.config = Configurator()
        
        self.config.add_route('auth-key', '/gridcentric/scalemanager/auth_key')
        self.config.add_view(self.set_auth_key, route_name='auth-key')
        
        self.config.add_route('new-ip', '/gridcentric/scalemanager/new-ip/{ipaddress}')
        self.config.add_view(self.new_ip_address, route_name='new-ip')

        self.config.add_route('service-action', '/gridcentric/scalemanager/services/{service_name}')
        self.config.add_view(self.handle_service_action, route_name='service-action')
        
        self.config.add_route('service-list', '/gridcentric/scalemanager/services')
        self.config.add_view(self.list_services, route_name='service-list')

        self.config.add_route('agent-stat', '/gridcentric/scalemanager/agent/{agent_name}')
        self.config.add_view(self.update_agent_stats, route_name='agent-stat')

    def get_wsgi_app(self):
        return self.config.make_wsgi_app()
     
    def authorized(request_handler):
        """
        A Decorator that does a simpel check to see if the request is authorized before
        executing the actual handler. 
        """
        def fn(self, context, request):
             if self._authorize(context, request):
                 return request_handler(self, context, request)
             else:
                 # Return an unauthorized response.
                return Response(status=401)
         
        return fn
    
    def _authorize(self, context, request):
        
        auth_hash = self.client.auth_hash()
        if auth_hash != None:
            auth_key = request.headers.get('X-Auth-Key', None)
            if auth_key != None:
                auth_token = self._get_auth_token(auth_key)
                return auth_hash == auth_token
            else:
                return False
        else:
            # If there is not auth hash then authentication has not been turned on
            # so all requests are allowed by default.
            return True

    def _get_auth_token(self, auth_key):
        salt = 'gridcentricscalemanager'
        return hashlib.sha1("%s%s" %(salt, auth_key)).hexdigest()
        
    @authorized
    def set_auth_key(self, context, request):
        """
        Updates the auth key in the system.
        """
        if request.method == 'POST':
            auth_key = json.loads(request.body)['auth_key']
            logging.info("Updating API Key.")
            self.client.set_auth_hash(self._get_auth_token(auth_key))
            
        return Response()
    
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
            logging.info("Retrieving service %s configuration" %(service_name))
            service_config = self.client.get_service_config(service_name)
            response = Response(body=json.dumps({'config':service_config}))
        elif request.method == "DELETE":
            logging.info("Unmanaging service %s" %(service_name))
            self.client.unmanage_service(service_name)
        elif request.method == "POST":
            service_config = json.loads(request.body)
            logging.info("Managing or updating service %s" %(service_name))
            self.client.update_service(service_name, service_config.get('config',""))
            
        return response
        
    @authorized
    def list_services(self, context, request):
        """
        Returns a list of services currently being managed.
        """
        services = self.client.list_managed_services()
        return Response(body=json.dumps({'services':services}))
    
    def new_ip_address(self, context, request):
        ip_address = request.matchdict['ipaddress']
        logging.info("New IP address %s has been recieved." % (ip_address))
        self.client.record_new_ipaddress(ip_address)
        return Response()
    
    def update_agent_stats(self, context, request):
        agent_name = request.matchdict['agent_name']
        logging.info("New stats from agent %s" % (agent_name))
        if request.method == 'POST':
            agent_stats = json.loads(request.body)
            for identifier, stats in agent_stats.iteritems():
                self.client.update_agent_stats(agent_name, identifier, str(stats))
        return Response()
    