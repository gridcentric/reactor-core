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
    
    def __init__(self, api_url):
        super(ScaleManagerApiClient, self).__init__()
        
        self.api_url = api_url
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

    def _authenticated_request(self, url, method, **kwargs):
        # TODO(dscannell) We need to figure out some authentication scheme so that only
        # authenticated requests can interact with the API. Once this scheme is figured out
        # we need to ensure that we are authenticated.
        
        resp, body = self.request(self.api_url + url, method, **kwargs)
        return resp, body

    def request(self, *args, **kwargs):
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        if 'body' in kwargs:
            kwargs['headers']['Content-Type'] = 'application/json'
            kwargs['body'] = json.dumps(kwargs['body'])

        resp, body = super(ScaleManagerApiClient, self).request(*args, **kwargs)

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
        
        self.config.add_route('new-ip', '/gridcentric/scalemanager/new-ip/{ipaddress}')
        self.config.add_view(self.new_ip_address, route_name='new-ip')

        self.config.add_route('service_action', '/gridcentric/scalemanager/services/{service_name}')
        self.config.add_view(self.handle_service_action, route_name='service_action')
        
        self.config.add_route('service-list', '/gridcentric/scalemanager/services')
        self.config.add_view(self.list_services, route_name='service-list')

    def get_wsgi_app(self):
        return self.config.make_wsgi_app()
    
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
    