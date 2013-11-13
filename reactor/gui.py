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

import os
import json
import traceback

from pyramid.httpexceptions import HTTPFound
from pyramid.response import Response
from pyramid.security import authenticated_userid
from pyramid.url import route_url as _route_url
from paste import httpserver

from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions

from . import server
from . api import connected
from . api import authorized
from . api import ReactorApi
from . api import HOST, PORT
from . endpoint import EndpointConfig
from . manager import ManagerConfig

# Because we are typically operating behind a reverse proxy,
# and wsgi/pyramid aren't able to determine what scheme the client
# is actually accessing us by, we need to fix up any links and
# redirections we produce by reading the X-Forwarded-Proto header
# sent to us by the proxy and substituting it for the default (http).
# This prevents us from, say, having the login form post to the HTTP
# port.
def fixup_url(url, request):
    scheme = request.headers.get('X-Forwarded-Proto', 'http') + '://'
    return url.replace('http://', scheme)

def route_url(route, request, **kw):
    url = _route_url(route, request, **kw)
    return fixup_url(url, request)

MIMEMAP = {
    "js": "application/json",
    "png": "image/png",
    "gif": "image/gif",
    "html": "text/html",
    "css": "text/css",
    "txt": "text/plain",
    "md": "text/html",
    "sh": "text/plain",
}

class ReactorGui(ReactorApi):

    def __init__(self, *args, **kwargs):
        super(ReactorGui, self).__init__(*args, **kwargs)

        # NOTE: We bind a collection of new endpoints onto the basic API
        # configuration. For some of these endpoints, we filter by accept type.
        # So if the user goes to the reactor URL in their web browser, they
        # will see the admin interface. If they use javascript embedded in a
        # page, they will get useable JSON.

        self.config.add_route(
            'admin-login', '/login', accept="text/html")
        self.config.add_route(
            'admin-login-form', '/login', accept="application/x-www-form-urlencoded")
        self.config.add_view(self.admin_login, route_name='admin-login')
        self.config.add_view(self.admin_login, route_name='admin-login-form')

        self.config.add_route(
            'admin-logout', '/logout', accept="text/html")
        self.config.add_route(
            'admin-logout-form', '/logout', accept="application/x-www-form-urlencoded")
        self.config.add_view(self.admin_logout, route_name='admin-logout')
        self.config.add_view(self.admin_logout, route_name='admin-logout-form')

        self.config.add_route('endpoint-info', '/endpoint')
        self.config.add_view(self.endpoint_info, route_name='endpoint-info')

        self.config.add_route('manager-info', '/manager')
        self.config.add_view(self.manager_info, route_name='manager-info')

        # Note: views are routed on a first-matched basis, so the ordering
        # of the following add_route calls are important since fetches to
        # /admin/assets could be matched by either the admin-asset or
        # admin-object routes (and we want them to go to admin-asset,
        # so that they can be fetched even in unathenticated contexts).
        self.config.add_route('admin-passwd', '/passwd')
        self.config.add_route('admin-asset', '/assets/{page_name:.*}')
        self.config.add_route('admin-page', '/{page_name}', accept="text/html")
        self.config.add_route('admin-object', '/{page_name}/{object_name:.*}', accept="text/html")

        self.config.add_view(self.admin_passwd, route_name='admin-passwd')
        self.config.add_view(self.admin_asset, route_name='admin-asset')
        self.config.add_view(self.index, route_name='admin-page')
        self.config.add_view(self.index, route_name='admin-object')

        self.config.add_view(context='pyramid.exceptions.NotFound',
            view='pyramid.view.append_slash_notfound_view')

    @connected
    @authorized(forbidden_view='self.admin_login')
    def manager_info(self, context, request):
        return Response(body=json.dumps(ManagerConfig().spec()))

    @connected
    @authorized(forbidden_view='self.admin_login')
    def endpoint_info(self, context, request):
        return Response(body=json.dumps(EndpointConfig().spec()))

    def _serve(self,
            context,
            request,
            base_dir=None,
            include_dirs=None,
            page_name=None,
            object_name=None,
            render_template=False,
            methods=None,
            **kwargs):

        if methods is None:
            methods = ('GET',)
        if page_name is None:
            page_name = request.matchdict.get('page_name') or 'index'
        if object_name is None:
            object_name = request.matchdict.get('object_name', '')
        if page_name.endswith('/'):
            page_name += 'index'

        if request.method in methods:

            # Find the real file.
            for ext in ['', '.html', '.md']:
                filename = os.path.join(base_dir, page_name + ext)
                if os.path.exists(filename):
                    break

            # Ensure we found it.
            if not(os.path.exists(filename)) or \
               not(os.path.isfile(filename)):
                return Response(status=404)

            try:
                raw_page_data = open(filename, 'r').read()

                # Render if necessary.
                if render_template:
                    lookup = TemplateLookup(directories=include_dirs)
                    template = Template(raw_page_data, lookup=lookup)
                    loggedin = authenticated_userid(request) is not None
                    template_args = {
                        "object": object_name,
                        "loggedin": loggedin,
                    }
                    template_args.update(kwargs)
                    page_data = template.render(**template_args)
                else:
                    page_data = raw_page_data

                # Check for supported types.
                ext = page_name.split('.')[-1]
                headers = {
                    "Content-type": MIMEMAP.get(ext, "text/html")
                }
            except Exception:
                traceback.print_exc()
                page_data = exceptions.html_error_template().render()
                headers = {
                    "Content-type": "text/html"
                }

            return Response(body=page_data, headers=headers)
        else:
            return Response(status=403)

    @connected
    @authorized(forbidden_view='self.admin_login')
    def index(self, context, request):
        """
        Render main admin page.
        """
        return self._serve(
            context,
            request,
            base_dir=os.path.join(
                os.path.dirname(__file__),
                'admin'),
            include_dirs=[
                os.path.join(
                    os.path.dirname(__file__),
                    'admin',
                    'include'),
            ],
            render_template=True)

    def admin_asset(self, context, request):
        """
        Render an asset (media, etc.).
        """
        return self._serve(
            context,
            request,
            base_dir=os.path.join(
                os.path.dirname(__file__),
                'admin',
                'assets'),
            render_template=False)

    @connected
    def admin_login(self, context, request):
        """
        Logs the admin user in.
        """
        login_url = route_url('admin-login', request)
        referrer = fixup_url(request.url, request)
        if referrer == login_url:
            referrer = route_url('admin-page', request, page_name='')
        came_from = request.params.get('came_from', referrer)
        url = route_url('admin-login', request)

        try:
            # See if the login form was submitted.
            response = self.login(context, request)
            return HTTPFound(location=came_from, headers=response.headers)
        except NotImplementedError:
            # Credentials not submitted or incorrect, render login page.
            if self._req_get_auth_key(request) != None:
                message = "Invalid credentials."
            else:
                message = ""

            return self._serve(
                context,
                request,
                base_dir=os.path.join(
                    os.path.dirname(__file__),
                    'admin'),
                include_dirs=[
                    os.path.join(
                        os.path.dirname(__file__),
                        'admin',
                        'include'),
                ],
                render_template=True,
                methods=('GET', 'POST'),
                page_name='login',
                came_from=came_from,
                message=message,
                url=url)

    def admin_logout(self, context, request):
        """
        Logs the admin user out.
        """
        response = self.logout(context, request)
        return HTTPFound(location=route_url('admin-login', request), headers=response.headers)

    @connected
    @authorized(forbidden_view='self.admin_login')
    def admin_passwd(self, context, request):
        """
        Sets the admin password.
        """
        # See if the password form was submitted.
        if 'auth_key' in request.params:
            # Set the new password.
            auth_key = request.params['auth_key']
            self.zkobj.auth_hash = self._create_admin_auth_token(auth_key)

            # Route user back to the home screen.
            return HTTPFound(location=route_url('admin-login', request))
        else:
            return self._serve(
                context,
                request,
                base_dir=os.path.join(
                    os.path.dirname(__file__),
                    'admin'),
                include_dirs=[
                    os.path.join(
                        os.path.dirname(__file__),
                        'admin',
                        'include'),
                ],
                render_template=True,
                page_name='passwd')

HELP = ("""Usage: reactor-gui [options]

    Run the API server (with GUI extension).

""",)

def gui_main(zk_servers, options):
    api = ReactorGui(zk_servers)
    app = api.get_wsgi_app()
    httpserver.serve(app, host=options.get("host"), port=options.get("port"))

def main():
    server.main(gui_main, [HOST, PORT], HELP)

if __name__ == "__main__":
    main()
