import json
import httplib2
import urllib

class ReactorApiClient(httplib2.Http):
    """
    A simple client that interacts with the REST interface of the reactorApi. This is to be
    used in third-party applications that want python bindings to interact with the system.
    """

    def __init__(self, api_url, api_key=None):
        super(ReactorApiClient, self).__init__()

        self.api_url = api_url
        self.api_key = api_key

        # Needed to httplib2.
        self.force_exception_to_status_code = True

    def version(self):
        """
        Return the API version.
        """
        resp, body = self._authenticated_request('/', 'GET')
        return body.get('version', None)

    def endpoint_list(self):
        """
        Returns a list of all the endpoints currently being managed by the reactor.
        """
        resp, body = self._authenticated_request('/v1.1/endpoints', 'GET')
        return body.get('endpoints', [])

    def endpoint_manage(self, endpoint_name, config):
        """
        Manage the endpoint using the given configuration.
        """
        self._authenticated_request('/v1.1/endpoints/%s' %
                                    endpoint_name, 'POST',
                                    body=config)

    def endpoint_unmanage(self, endpoint_name):
        """
        Unmanage the endpoint.
        """
        self._authenticated_request('/v1.1/endpoints/%s' %
                                    endpoint_name, 'DELETE')

    def endpoint_config(self, endpoint_name):
        """
        Return the endpoint's configuration.
        """
        resp, body = self._authenticated_request('/v1.1/endpoints/%s' %
                                                 endpoint_name, 'GET')
        return body

    def manager_list(self, active=False):
        """
        Returns a list of all managers.
        """
        resp, body = self._authenticated_request('/v1.1/managers', 'GET')
        if active:
            return body.get('active', [])
        else:
            return body.get('configured', [])

    def manager_update(self, manager, config):
        """
        Update the manager with the given configuration.
        """
        self._authenticated_request('/v1.1/managers/%s' %
                                    manager, 'POST',
                                    body=config)

    def manager_config(self, manager):
        """
        Return the manager's configuration.
        """
        resp, body = self._authenticated_request('/v1.1/managers/%s' %
                                                 manager, 'GET')
        return body

    def manager_reset(self, manager):
        """
        Remove the given manager's configuration.
        """
        resp, body = self._authenticated_request('/v1.1/managers/%s' %
                                                 manager, 'DELETE')

    def endpoint_ip_addresses(self, endpoint_name):
        """
        Returns a list of the ip addresses (both dynamically confirmed and
        manually configured) for this endpoint.
        """
        resp, body = self._authenticated_request('/v1.1/endpoints/%s/ips' %
                                                 endpoint_name, 'GET')
        return body.get('ip_addresses', [])

    def endpoint_action(self, endpoint_name, action):
        """
        Set the current endpoint action.
        """
        resp, body = self._authenticated_request('/v1.1/endpoints/%s/state' %
                                                 endpoint_name, 'POST',
                                                 body={"action": action})
        return body

    def endpoint_state(self, endpoint_name):
        """
        Return available live endpoint info.
        """
        resp, body = self._authenticated_request('/v1.1/endpoints/%s/state' %
                                                 endpoint_name, 'GET')
        return body

    def endpoint_metrics(self, endpoint_name):
        """
        Set the custom endpoint metrics.
        """
        resp, body = self._authenticated_request('/v1.1/endpoints/%s/metrics' %
                                                 endpoint_name, 'GET')
        return body

    def endpoint_metrics_set(self, endpoint_name, metrics):
        """
        Set the custom endpoint metrics.
        """
        self._authenticated_request('/v1.1/endpoints/%s/metrics' %
                                    endpoint_name, 'POST',
                                    body=metrics)

    def endpoint_log(self, endpoint_name):
        """
        Return the full endpoint log.
        """
        resp, body = self._authenticated_request('/v1.1/endpoints/%s/log' %
                                                 endpoint_name, 'GET')
        return body

    def session_list(self, endpoint_name):
        """
        Return a list of active sessions.
        """
        resp, body = self._authenticated_request('/v1.1/endpoints/%s/sessions' %
                                                 endpoint_name, 'GET')
        return body

    def session_kill(self, endpoint_name, session):
        """
        Drop a specific session.
        """
        resp, body = self._authenticated_request('/v1.1/endpoints/%s/sessions/%s' %
                                                 (endpoint_name, session), 'DELETE')
        return body

    def register_ip(self, ip):
        """
        Register the given IP.
        """
        self._authenticated_request('/v1.1/register/%s' %
                                    ip, 'POST')

    def drop_ip(self, ip):
        """
        Unregister the given IP.
        """
        self._authenticated_request('/v1.1/unregister/%s' %
                                    ip, 'POST')

    def api_key_set(self, api_key):
        """
        Changes the API key in the system.
        """
        self._authenticated_request('/v1.1/auth_key',
                                    'POST',
                                    body={'auth_key': api_key})

    def _authenticated_request(self, url, method, **kwargs):
        if self.api_key != None:
            # Log in and get a cookie.
            body = {'auth_key' : self.api_key}
            headers = {'Content-type': 'application/x-www-form-urlencoded'}
            resp, _ = super(ReactorApiClient, self).request(
                self.api_url + '/admin/login', 'POST',
                headers=headers,
                body=urllib.urlencode(body))
            if 'set-cookie' not in resp:
                raise Exception("Error: invalid password.")
            kwargs.setdefault('headers', {})['Cookie'] = resp['set-cookie']

        resp, body = self.request(self.api_url + url, method, **kwargs)
        return resp, body

    def request(self, *args, **kwargs):
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        if 'body' in kwargs:
            kwargs['headers']['Content-Type'] = 'application/json'
            kwargs['body'] = json.dumps(kwargs['body'])

        resp, body = super(ReactorApiClient, self).request(*args, **kwargs)
        if resp.status != 200:
            raise Exception("Error (status=%s): %s" % (resp.status, str(body)))
        if body:
            try:
                body = json.loads(body)
            except ValueError, e:
                pass
        return resp, body
