import threading
import traceback
import logging
import json
import os
import uuid

from pyramid.httpexceptions import HTTPFound
from pyramid.response import Response
from pyramid.security import remember, forget, authenticated_userid
from pyramid.url import route_url
from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions

from reactor.api import ReactorApi
from reactor.api import connected
from reactor.api import authorized
from reactor.api import authorized_admin_only

from reactor.server.manager import ReactorScaleManager
import reactor.server.ips as ips
import reactor.server.config as config

class ServerApi(ReactorApi):
    def __init__(self, zk_servers):
        self.manager = None
        self.manager_running = False
        ReactorApi.__init__(self, zk_servers)

        self.config.add_route('api-servers', '/api_servers')
        self.config.add_view(self.set_api_servers, route_name='api-servers')

        self.config.add_route('endpoint-info', '/endpoint')
        self.config.add_view(self.endpoint_info, route_name='endpoint-info')

        self.config.add_route('manager-info', '/manager')
        self.config.add_view(self.manager_info, route_name='manager-info')

        # Add a login page.
        self.config.add_route('admin-login', '/admin/login')
        self.config.add_view(self.admin_login, route_name='admin-login')

        # Add a logout page.
        self.config.add_route('admin-logout', '/admin/logout')
        self.config.add_view(self.admin_logout, route_name='admin-logout')

        # Note: views are routed on a first-matched basis, so the ordering
        # of the following add_route calls are important since fetches to
        # /admin/assets could be matched by either the admin-asset or
        # admin-object routes (and we want them to go to admin-asset,
        # so that they can be fetched even in unathenticated contexts).
        self.config.add_route('admin-home', '/admin/')
        self.config.add_route('admin-passwd', '/admin/passwd')
        self.config.add_route('admin-asset', '/admin/assets/{object_name:.*}')
        self.config.add_route('admin-page', '/admin/{page_name}')
        self.config.add_route('admin-object', '/admin/{page_name}/{object_name:.*}')
        self.config.add_view(self.admin, route_name='admin-home')
        self.config.add_view(self.admin_passwd, route_name='admin-passwd')
        self.config.add_view(self.admin_asset, route_name='admin-asset')
        self.config.add_view(self.admin, route_name='admin-page')
        self.config.add_view(self.admin, route_name='admin-object')
        self.config.add_view(context='pyramid.exceptions.NotFound',
                view='pyramid.view.append_slash_notfound_view')

        # Check the endpoint.
        self.check(zk_servers)

    def handle_update_manager(self, manager, manager_config):
        errs = self.manager._manager_config_validate(manager_config)
        if errs:
            return json.dumps(errs)
        else:
            return ReactorApi.handle_update_manager(self, manager, manager_config)

    @connected
    def manager_info(self, context, request):
        return Response(body=json.dumps(self.manager._manager_config_spec()))

    def handle_update_endpoint(self, endpoint_name, endpoint_config):
        errs = self.manager._endpoint_config_validate(endpoint_config)
        if errs:
            return json.dumps(errs)
        else:
            return ReactorApi.handle_update_endpoint(self, endpoint_name, endpoint_config)

    @connected
    def endpoint_info(self, context, request):
        return Response(body=json.dumps(self.manager._endpoint_config_spec()))

    @connected
    def admin_login(self, context, request):
        """
        Logs the admin user in.
        """
        login_url = route_url('admin-login', request)
        referrer = request.url
        if referrer == login_url:
            referrer = '/admin/'
        came_from = request.params.get('came_from', referrer)
        message = ''

        # See if the login form was submitted.
        if 'auth_key' in request.params:
            auth_key = request.params['auth_key']
            if self.check_admin_auth_key(auth_key):
                headers = remember(request, 'admin')
                return HTTPFound(location = came_from,
                                 headers = headers)
            message = 'Incorrect password.'

        # Credentials not submitted or incorrect, render login page.
        filename = os.path.join(os.path.dirname(__file__), 'admin', 'login.html')
        lookup_path = os.path.join(os.path.dirname(__file__), 'admin', 'include')
        lookup = TemplateLookup(directories=[lookup_path])
        template = Template(filename=filename, lookup=lookup)
        kwargs = { 'message' :  message,
                   'url' : route_url('admin-login', request),
                   'came_from' : came_from,
                   'user' : '',
                   'loggedin' : False }

        body = template.render(**kwargs)
        return Response(body=body)

    def admin_logout(self, context, request):
        """
        Logs the admin user out.
        """
        headers = forget(request)
        return HTTPFound(location=route_url('admin-home', request), headers=headers)

    @connected
    @authorized_admin_only
    def set_api_servers(self, context, request):
        """
        Updates the list of API servers in the system.
        """
        if request.method == 'POST':
            api_servers = json.loads(request.body)['api_servers']
            logging.info("Updating API Servers.")
            self.reconnect(api_servers)
            return Response()

        elif request.method == 'GET':
            return Response(body=json.dumps({ "api_servers" : self.zk_servers }))

        else:
            return Response(status=403)

    @connected
    @authorized_admin_only(forbidden_view='self.admin_login')
    def admin(self, context, request):
        """
        Render a page from the admin directory and write it back.
        """
        if request.method == 'GET':
            # Read the page_name from the request.
            page_name = request.matchdict.get('page_name', 'index')
            object_name = request.matchdict.get('object_name', '')

            if object_name and page_name.endswith('s'):
                page_name = page_name[:-1]
            if page_name.find('.') < 0:
                page_name += '.html'

            # Check that the file exists.
            filename = os.path.join(os.path.dirname(__file__), 'admin', page_name)
            if not(os.path.exists(filename)):
                return Response(status=404)

            # Render it.
            lookup_path = os.path.join(os.path.dirname(__file__), 'admin', 'include')
            lookup = TemplateLookup(directories=[lookup_path])
            template = Template(filename=filename, lookup=lookup)
            kwargs = { "object" : object_name,
                       "user" : 'admin',
                       "loggedin" : authenticated_userid(request) != None }
            try:
                page_data = template.render(**kwargs)
            except:
                page_data = exceptions.html_error_template().render()

            return Response(body=page_data)

        else:
            return Response(status=403)

    def admin_asset(self, context, request):
        """
        Render an asset for the admin page
        """
        if request.method == 'GET':
            # Read the page_name from the request.
            object_name = request.matchdict.get('object_name', '')
            page_name = os.path.join('assets', object_name)

            # Check that the file exists.
            filename = os.path.join(os.path.dirname(__file__), 'admin', page_name)
            if not(os.path.exists(filename)):
                return Response(status=404)

            page_data = open(filename).read()

            # Check for supported types.
            ext = page_name.split('.')[-1]
            mimemap = {
                "js": "application/json",
                "png": "image/png",
                "gif": "image/gif",
                "html": "text/html",
                "css": "text/css"
            }

            return Response(body=page_data,
                            headers={"Content-type" : mimemap[ext]})
        else:
            return Response(status=403)

    @connected
    @authorized_admin_only(forbidden_view='self.admin_login')
    def admin_passwd(self, context, request):
        """
        Sets the admin password.
        """

        # See if the password form was submitted.
        if 'auth_key' in request.params:
            # Set the new password.
            auth_key = request.params['auth_key']
            self.client.set_auth_hash(self._create_admin_auth_token(auth_key))

            # Route user back to the home screen.
            return HTTPFound(location=route_url('admin-home', request))

        # New password not submitted, render password page.
        filename = os.path.join(os.path.dirname(__file__), 'admin', 'passwd.html')
        lookup_path = os.path.join(os.path.dirname(__file__), 'admin', 'include')
        lookup = TemplateLookup(directories=[lookup_path])
        template = Template(filename=filename, lookup=lookup)
        kwargs = {
            'user': 'admin',
            'loggedin': authenticated_userid(request) != None
        }
        body = template.render(**kwargs)
        return Response(body=body)

    def start_manager(self, zk_servers):
        zk_servers.sort()
        self.zk_servers.sort()
        if self.zk_servers != zk_servers:
            self.stop_manager()

        def manager_run():
            try:
                self.manager.run()
            except:
                error = traceback.format_exc()
                logging.error("An unrecoverable error occurred: %s" % error)

        if not(self.manager_running):
            self.manager = ReactorScaleManager(zk_servers)
            self.manager_thread = threading.Thread(target=manager_run)
            self.manager_thread.daemon = True
            self.manager_thread.start()
            self.manager_running = True

    def stop_manager(self):
        if self.manager_running:
            self.manager.clean_stop()
            self.manager_thread.join()
            self.manager_running = False

    def check(self, zk_servers):
        is_local = ips.any_local(zk_servers)

        if not(is_local):
            # Ensure that Zookeeper is stopped.
            config.ensure_stopped()
            config.check_config(zk_servers)

        else:
            # Ensure that Zookeeper is started.
            logging.info("Starting Zookeeper.")
            config.check_config(zk_servers)
            config.ensure_started()

        # NOTE: We now *always* start the manager. We rely on the user to
        # actually deactivate it or set the number of keys appropriately when
        # they do not want it to be used to power endpoints.
        self.start_manager(zk_servers)

    def reconnect(self, zk_servers):
        # Check that we are running correctly.
        self.check(zk_servers)

        # Call the base API to reconnect.
        ReactorApi.reconnect(self, zk_servers)
