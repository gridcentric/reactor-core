import json
import httplib2

class ReactorApiClient(httplib2.Http):
    """
    A simple client that interacts with the REST interface of the API.

    This is to be used by the CLI and possibly in third-party applications that
    want python bindings to interact with the system.
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
        _, body = self.request('/', 'GET')
        return body.get('version', None)

    def url(self):
        """
        Return the API URL.
        """
        _, body = self.request('/v1.1/url', 'GET')
        return body.get('url', None)

    def url_set(self, url):
        """
        Changes the API URL in the system.
        """
        self.request('/v1.1/url', 'POST', body={'url': url})

    def endpoint_list(self):
        """
        Returns a list of all the endpoints currently being managed by the reactor.
        """
        _, body = self.request('/v1.1/endpoints', 'GET')
        return body.get('endpoints', [])

    def endpoint_manage(self, endpoint_name, config):
        """
        Manage the endpoint using the given configuration.
        """
        self.request('/v1.1/endpoints/%s' % endpoint_name, 'POST', body=config)

    def endpoint_unmanage(self, endpoint_name):
        """
        Unmanage the endpoint.
        """
        self.request('/v1.1/endpoints/%s' % endpoint_name, 'DELETE')

    def endpoint_config(self, endpoint_name):
        """
        Return the endpoint's configuration.
        """
        _, body = self.request('/v1.1/endpoints/%s' % endpoint_name, 'GET')
        return body

    def manager_list(self, active=False):
        """
        Returns a list of all managers.
        """
        _, body = self.request('/v1.1/managers', 'GET')
        if active:
            return body.get('active', [])
        else:
            return body.get('configured', [])

    def manager_update(self, manager, config):
        """
        Update the manager with the given configuration.
        """
        self.request('/v1.1/managers/%s' % manager, 'POST', body=config)

    def manager_config(self, manager):
        """
        Return the manager's configuration.
        """
        _, body = self.request('/v1.1/managers/%s' % manager, 'GET')
        return body

    def manager_reset(self, manager):
        """
        Remove the given manager's configuration.
        """
        self.request('/v1.1/managers/%s' % manager, 'DELETE')

    def endpoint_ip_addresses(self, endpoint_name):
        """
        Returns a list of the dynamic ip addresses for this endpoint.
        """
        _, body = self.request('/v1.1/endpoints/%s/ips' % endpoint_name, 'GET')
        return body.get('ip_addresses', [])

    def endpoint_action(self, endpoint_name, action):
        """
        Set the current endpoint action.
        """
        _, body = self.request(
            '/v1.1/endpoints/%s/state' % endpoint_name, 'POST', body={"action": action})
        return body

    def endpoint_state(self, endpoint_name):
        """
        Return available live endpoint info.
        """
        _, body = self.request('/v1.1/endpoints/%s/state' % endpoint_name, 'GET')
        return body

    def endpoint_metrics(self, endpoint_name):
        """
        Set the custom endpoint metrics.
        """
        _, body = self.request('/v1.1/endpoints/%s/metrics' % endpoint_name, 'GET')
        return body

    def endpoint_metrics_set(self, endpoint_name, metrics):
        """
        Set the custom endpoint metrics.
        """
        self.request(
            '/v1.1/endpoints/%s/metrics' % endpoint_name, 'POST', body=metrics)

    def endpoint_log(self, endpoint_name):
        """
        Return the full endpoint log.
        """
        _, body = self.request('/v1.1/endpoints/%s/log' % endpoint_name, 'GET')
        return body

    def session_list(self, endpoint_name):
        """
        Return a list of active sessions.
        """
        _, body = self.request('/v1.1/endpoints/%s/sessions' % endpoint_name, 'GET')
        return body

    def session_kill(self, endpoint_name, session):
        """
        Drop a specific session.
        """
        self.request(
            '/v1.1/endpoints/%s/sessions/%s' % (endpoint_name, session), 'DELETE')

    def register_ip(self, ip):
        """
        Register the given IP.
        """
        self.request('/v1.1/register/%s' % ip, 'POST')

    def drop_ip(self, ip):
        """
        Unregister the given IP.
        """
        self.request('/v1.1/unregister/%s' % ip, 'POST')

    def api_key_set(self, api_key):
        """
        Changes the API key in the system.
        """
        self.request('/v1.1/auth_key', 'POST', body={'auth_key': api_key})

    def _authenticated_request(self, url, method, body=None):
        headers = {}
        resp, body = self.request(self.api_url + url, method, headers=headers, body=body)
        return resp, body

    def request(self, url, method, *args, **kwargs):
        headers = kwargs.get('headers', {})
        headers['Accept'] = 'application/json'
        if self.api_key != None:
            headers['X-Auth-Key'] = self.api_key
        kwargs['headers'] = headers

        if kwargs.get('body'):
            kwargs['body'] = json.dumps(kwargs['body'])

        resp, body = super(ReactorApiClient, self).request(
            self.api_url + url, method, *args, **kwargs)

        if resp.status != 200:
            raise Exception("Error (status=%s): %s" % (resp.status, str(body)))
        if body:
            try:
                body = json.loads(body)
            except ValueError:
                pass
        return resp, body
