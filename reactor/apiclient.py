# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

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
        return body

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

    def endpoint_alias(self, endpoint_name, new_name):
        """
        Alias the endpoint.
        """
        self.request('/v1.1/endpoints/%s/alias' % endpoint_name, 'POST', body=new_name)

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

    def manager_forget(self, manager):
        """
        Remove the given manager's configuration.
        """
        self.request('/v1.1/managers/%s' % manager, 'DELETE')

    def endpoint_ips(self, endpoint_name=None):
        """
        Returns a list of the dynamic ip addresses for this endpoint.
        """
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint/ips', 'GET')
        else:
            _, body = self.request('/v1.1/endpoints/%s/ips' % endpoint_name, 'GET')
        return body

    def endpoint_action(self, endpoint_name=None, action=None):
        """
        Set the current endpoint action.
        """
        if action is None:
            raise Exception("Action required!")
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint/state',
                'POST', body={"action": action})
        else:
            _, body = self.request('/v1.1/endpoints/%s/state' % endpoint_name,
                'POST', body={"action": action})
        return body

    def endpoint_state(self, endpoint_name=None):
        """
        Return available live endpoint info.
        """
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint/state', 'GET')
        else:
            _, body = self.request('/v1.1/endpoints/%s/state' % endpoint_name, 'GET')
        return body

    def endpoint_metrics(self, endpoint_name=None):
        """
        Set the custom endpoint metrics.
        """
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint/metrics', 'GET')
        else:
            _, body = self.request('/v1.1/endpoints/%s/metrics' % endpoint_name, 'GET')
        return body

    def endpoint_metrics_set(self, endpoint_name=None, metrics=None):
        """
        Set the custom endpoint metrics.
        """
        if metrics is None:
            raise Exception("Metrics required!")
        if endpoint_name is None:
            self.request('/v1.1/endpoint/metrics', 'POST', body=metrics)
        else:
            self.request('/v1.1/endpoints/%s/metrics' % endpoint_name, 'POST', body=metrics)

    def endpoint_log(self, endpoint_name=None, since=None):
        """
        Return the full endpoint log.
        """
        if endpoint_name is None:
            url = '/v1.1/endpoint/log'
        else:
            url = '/v1.1/endpoints/%s/log' % endpoint_name
        if since is not None:
            url += '?since=%f' % float(since)
        _, body = self.request(url, 'GET')
        return body

    def endpoint_post(self, endpoint_name=None, message=None, level=None):
        """
        Post a message to the endpoint log.
        """
        if message is None:
            raise Exception("Message required!")
        if endpoint_name is None:
            url = '/v1.1/endpoint/log'
        else:
            url = '/v1.1/endpoints/%s/log' % endpoint_name
        if level is not None:
            url += '?level=%s' % level
        _, body = self.request(url, 'POST', body=message)
        return body

    def session_list(self, endpoint_name=None):
        """
        Return a list of active sessions.
        """
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint/sessions', 'GET')
        else:
            _, body = self.request('/v1.1/endpoints/%s/sessions' % endpoint_name, 'GET')
        return body

    def session_kill(self, endpoint_name=None, session=None):
        """
        Drop a specific session.
        """
        if session is None:
            raise Exception("Session required!")
        if endpoint_name is None:
            self.request('/v1.1/endpoint/sessions/%s' %
                (session), 'DELETE')
        else:
            self.request('/v1.1/endpoints/%s/sessions/%s' %
                (endpoint_name, session), 'DELETE')

    def register_ip(self, ip=None):
        """
        Register the given IP.
        """
        if ip is None:
            self.request('/v1.1/register', 'POST')
        else:
            self.request('/v1.1/register/%s' % ip, 'POST')

    def drop_ip(self, ip=None):
        """
        Unregister the given IP.
        """
        if ip is None:
            self.request('/v1.1/unregister', 'POST')
        else:
            self.request('/v1.1/unregister/%s' % ip, 'POST')

    def associate(self, endpoint_name=None, instance_id=None):
        """
        Associate an instance with an endpoint.
        """
        if instance_id is None:
            raise Exception("Instance required!")
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint/instances/%s' %
                instance_id, 'POST')
        else:
            _, body = self.request('/v1.1/endpoints/%s/instances/%s' %
                (endpoint_name, instance_id), 'POST')
        return body

    def disassociate(self, endpoint_name=None, instance_id=None):
        """
        Disassociate an instance from an endpoint.
        """
        if instance_id is None:
            raise Exception("Instance required!")
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint/instances/%s' %
                instance_id, 'DELETE')
        else:
            _, body = self.request('/v1.1/endpoints/%s/instances/%s' %
                (endpoint_name, instance_id), 'DELETE')
        return body

    def instances(self, endpoint_name=None):
        """
        Return a map of all instances.
        """
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint/instances', 'GET')
        else:
            _, body = self.request('/v1.1/endpoints/%s/instances' % endpoint_name, 'GET')
        return body

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
        headers['Content-Type'] = 'application/json'
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
