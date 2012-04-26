#!/usr/bin/env python

import json
import httplib2

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

    def list_managers_configured(self):
        """
        Returns a list of all configured managers.
        """
        resp, body = self._authenticated_request('/gridcentric/pancake/managers', 'GET')
        return body.get('managers_configured',[])

    def list_managers_active(self):
        """
        Returns a list of all active managers.
        """
        resp, body = self._authenticated_request('/gridcentric/pancake/managers', 'GET')
        return body.get('managers_active',[])

    def update_manager(self, manager, config):
        """
        Update the manager with the given configuration.
        """
        self._authenticated_request('/gridcentric/pancake/managers/%s' %
                                    (manager or 'default'), 'POST',
                                    body={'config':config})

    def get_manager_config(self, manager):
        """
        Return the manager's configuration.
        """
        resp, body = self._authenticated_request('/gridcentric/pancake/managers/%s' %
                                                 (manager or 'default'), 'GET')
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
        return resp, body

    def request(self, *args, **kwargs):
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        if 'body' in kwargs:
            kwargs['headers']['Content-Type'] = 'application/json'
            kwargs['body'] = json.dumps(kwargs['body'])

        resp, body = super(PancakeApiClient, self).request(*args, **kwargs)

        if resp.status != 200:
            raise Exception(body)
        if body:
            try:
                body = json.loads(body)
            except ValueError, e:
                pass

        return resp, body
