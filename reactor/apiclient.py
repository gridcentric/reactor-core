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

    def endpoint_create(self, endpoint_name=None, config=None):
        """
        Create the endpoint using the given configuration.
        """
        if config is None:
            raise Exception("Config required!")
        if endpoint_name is None:
            self.request('/v1.1/endpoint', 'PUT', body=config)
        else:
            self.request('/v1.1/endpoints/%s' % endpoint_name, 'PUT', body=config)

    def endpoint_update(self, endpoint_name=None, config=None):
        """
        Update the endpoint using the given configuration.
        """
        if config is None:
            raise Exception("Config required!")
        if endpoint_name is None:
            self.request('/v1.1/endpoint', 'POST', body=config)
        else:
            self.request('/v1.1/endpoints/%s' % endpoint_name, 'POST', body=config)

    def endpoint_remove(self, endpoint_name=None):
        """
        Remove the endpoint.
        """
        if endpoint_name is None:
            self.request('/v1.1/endpoint', 'DELETE')
        else:
            self.request('/v1.1/endpoints/%s' % endpoint_name, 'DELETE')

    def endpoint_alias(self, endpoint_name=None, new_name=None):
        """
        Alias the endpoint.
        """
        if new_name is None:
            raise Exception("New name required!")
        if endpoint_name is None:
            self.request('/v1.1/endpoint/alias', 'POST', body=new_name)
        else:
            self.request('/v1.1/endpoints/%s/alias' % endpoint_name, 'POST', body=new_name)

    def endpoint_config(self, endpoint_name=None):
        """
        Return the endpoint's configuration.
        """
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint', 'GET')
        else:
            _, body = self.request('/v1.1/endpoints/%s' % endpoint_name, 'GET')
        return body

    def manager_configs_list(self):
        """
        Returns a list of all configured managers.
        """
        _, body = self.request('/v1.1/managers/configs', 'GET')
        return body

    def manager_active_list(self):
        """
        Returns a list of all running managers.
        """
        _, body = self.request('/v1.1/managers/active', 'GET')
        return body

    def manager_update(self, manager, config):
        """
        Update the manager with the given configuration.
        """
        self.request('/v1.1/managers/configs/%s' % manager, 'POST', body=config)

    def manager_config(self, manager):
        """
        Return the manager's configuration.
        """
        _, body = self.request('/v1.1/managers/configs/%s' % manager, 'GET')
        return body

    def manager_info(self, manager):
        """
        Return the active manager info.
        """
        _, body = self.request('/v1.1/managers/active/%s' % manager, 'GET')
        return body

    def manager_log(self, manager, since=None):
        """
        Return the manager log.
        """
        url = '/v1.1/managers/log/%s' % manager
        if since is not None:
            url += '?since=%f' % float(since)
        _, body = self.request(url, 'GET')
        return body

    def manager_remove(self, manager):
        """
        Remove the given manager's configuration.
        """
        self.request('/v1.1/managers/configs/%s' % manager, 'DELETE')

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

    def metadata_list(self, endpoint_name=None):
        """
        List all available metadata.
        """
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint/metadata', 'GET')
        else:
            _, body = self.request('/v1.1/endpoints/%s/metadata' % endpoint_name, 'GET')
        return body

    def metadata_get(self, endpoint_name=None, key=None):
        """
        Get the given metadata key.
        """
        if endpoint_name is None:
            _, body = self.request('/v1.1/endpoint/metadata/%s' % key, 'GET')
        else:
            _, body = self.request('/v1.1/endpoints/%s/metadata/%s' % (endpoint_name, key), 'GET')
        return body

    def metadata_set(self, endpoint_name=None, key=None, value=None):
        """
        Get the given metadata key.
        """
        if key is None:
            raise Exception("Key required!")
        if endpoint_name is None:
            self.request('/v1.1/endpoint/metadata/%s' % key, 'POST', body=value)
        else:
            self.request('/v1.1/endpoints/%s/metadata/%s' %
                (endpoint_name, key), 'POST', body=value)

    def metadata_delete(self, endpoint_name=None, key=None):
        """
        Get the given metadata key.
        """
        if key is None:
            raise Exception("Key required!")
        if endpoint_name is None:
            self.request('/v1.1/endpoint/metadata/%s' % key, 'DELETE')
        else:
            self.request('/v1.1/endpoints/%s/metadata/%s' % (endpoint_name, key), 'DELETE')

    def ip_register(self, ip=None):
        """
        Register the given IP.
        """
        if ip is None:
            self.request('/v1.1/register', 'POST')
        else:
            self.request('/v1.1/register/%s' % ip, 'POST')

    def ip_drop(self, ip=None):
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
            self.request('/v1.1/endpoint/instances/%s' % instance_id, 'POST')
        else:
            self.request('/v1.1/endpoints/%s/instances/%s' % (endpoint_name, instance_id), 'POST')

    def disassociate(self, endpoint_name=None, instance_id=None):
        """
        Disassociate an instance from an endpoint.
        """
        if instance_id is None:
            raise Exception("Instance required!")
        if endpoint_name is None:
            self.request('/v1.1/endpoint/instances/%s' % instance_id, 'DELETE')
        else:
            self.request('/v1.1/endpoints/%s/instances/%s' %
                (endpoint_name, instance_id), 'DELETE')

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
