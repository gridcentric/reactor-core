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

    def version(self):
        """
        Return the API version.
        """
        resp, body = self._authenticated_request('/', 'GET')
        return body.get('version', None)

    def list_managed_endpoints(self):
        """
        Returns a list of all the endpoints currently being managed by the pancake.
        """
        resp, body = self._authenticated_request('/v1.0/endpoints', 'GET')
        return body.get('endpoints', [])

    def manage_endpoint(self, endpoint_name, config):
        """
        Manage the endpoint using the given configuration.
        """
        self._authenticated_request('/v1.0/endpoints/%s' % (endpoint_name),
                                    'POST',
                                    body={'config':config})

    def unmanage_endpoint(self, endpoint_name):
        """
        Unmanage the endpoint.
        """
        self._authenticated_request('/v1.0/endpoints/%s' % (endpoint_name), 'DELETE')

    def get_endpoint_config(self, endpoint_name):
        """
        Return the endpoint's configuration.
        """
        resp, body = self._authenticated_request('/v1.0/endpoints/%s' %
                                                 endpoint_name, 'GET')
        return body.get('config', "")

    def list_managers_configured(self):
        """
        Returns a list of all configured managers.
        """
        resp, body = self._authenticated_request('/v1.0/managers', 'GET')
        return body.get('managers_configured', [])

    def list_managers_active(self):
        """
        Returns a list of all active managers.
        """
        resp, body = self._authenticated_request('/v1.0/managers', 'GET')
        return body.get('managers_active', [])

    def update_manager(self, manager, config):
        """
        Update the manager with the given configuration.
        """
        self._authenticated_request('/v1.0/managers/%s' %
                                    (manager or 'default'), 'POST',
                                    body={'config':config})

    def get_manager_config(self, manager):
        """
        Return the manager's configuration.
        """
        resp, body = self._authenticated_request('/v1.0/managers/%s' %
                                                 (manager or 'default'), 'GET')
        return body.get('config', "")

    def remove_manager_config(self, manager):
        """
        Remove the given manager's configuration.
        """
        resp, body = self._authenticated_request('/v1.0/managers/%s' % manager,
                                                 'DELETE')

    def list_endpoint_ips(self, endpoint_name):
        """
        Returns a list of the ip addresses (both dynamically confirmed and
        manually configured) for this endpoint.
        """
        resp, body = self._authenticated_request('/v1.0/endpoints/%s/ips' %
                                                 endpoint_name, 'GET')
        return body.get('ip_addresses', [])

    def set_endpoint_action(self, endpoint_name, action):
        """
        Set the current endpoint action.
        """
        resp, body = self._authenticated_request('/v1.0/endpoints/%s/state' %
                                                 endpoint_name, 'POST',
                                                 body={ "action" : action })
        return body

    def get_endpoint_state(self, endpoint_name):
        """
        Return available live endpoint info.
        """
        resp, body = self._authenticated_request('/v1.0/endpoints/%s/state' %
                                                 endpoint_name, 'GET')
        return body

    def get_endpoint_metrics(self, endpoint_name):
        """
        Set the custom endpoint metrics.
        """
        resp, body = self._authenticated_request('/v1.0/endpoints/%s/metrics' %
                                                 endpoint_name, 'GET')
        return body

    def set_endpoint_metrics(self, endpoint_name, metrics):
        """
        Set the custom endpoint metrics.
        """
        self._authenticated_request('/v1.0/endpoints/%s/metrics' %
                                    endpoint_name, 'POST', body=metrics)

    def update_api_key(self, api_key):
        """
        Changes the API key in the system.
        """
        self._authenticated_request('/v1.0/auth_key',
                                    'POST', body={'auth_key':api_key})

    def get_domain(self):
        """
        Gets the current pancake domain.
        """
        resp, body = self._authenticated_request('/v1.0/domain', 'GET')
        return body.get("domain", '')

    def set_domain(self, domain):
        """
        Sets the current pancake domain.
        """
        self._authenticated_request('/v1.0/domain',
                                    'POST', body={'domain':domain})

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
            raise Exception("Error (status=%s): %s" % (resp.status, str(body)))
        if body:
            try:
                body = json.loads(body)
            except ValueError, e:
                pass

        return resp, body
