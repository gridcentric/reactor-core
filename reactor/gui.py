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
import threading
import markdown

from pyramid.httpexceptions import HTTPFound
from pyramid.response import Response
from pyramid.security import authenticated_userid
from pyramid.url import route_url as _route_url

from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions

from . api import connected
from . api import authorized
from . api import ReactorApiExtension
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
    "sh": "text/plain",
}

class ReactorGui(ReactorApiExtension):

    def __init__(self, api, *args, **kwargs):
        super(ReactorGui, self).__init__(api, *args, **kwargs)

        # Set the index.
        self.api.index = self.admin

        # NOTE: We bind a collection of new endpoints onto
        # the basic API configuration. For some of these endpoints,
        # we filter by accept type. So if the user goes to the
        # reactor URL in their web browser, they will see the admin
        # interface. If they use javascript embedded in a page, they
        # will get useable JSON.

        api.config.add_route(
            'admin-login', '/login', accept="text/html")
        api.config.add_route(
            'admin-login-form', '/login', accept="application/x-www-form-urlencoded")
        api.config.add_view(self.admin_login, route_name='admin-login')
        api.config.add_view(self.admin_login, route_name='admin-login-form')

        api.config.add_route(
            'admin-logout', '/logout', accept="text/html")
        api.config.add_route(
            'admin-logout-form', '/logout', accept="application/x-www-form-urlencoded")
        api.config.add_view(self.admin_logout, route_name='admin-logout')
        api.config.add_view(self.admin_logout, route_name='admin-logout-form')

        api.config.add_route('endpoint-info', '/endpoint')
        api.config.add_view(self.endpoint_info, route_name='endpoint-info')

        api.config.add_route('manager-info', '/manager')
        api.config.add_view(self.manager_info, route_name='manager-info')

        # Note: views are routed on a first-matched basis, so the ordering
        # of the following add_route calls are important since fetches to
        # /admin/assets could be matched by either the admin-asset or
        # admin-object routes (and we want them to go to admin-asset,
        # so that they can be fetched even in unathenticated contexts).
        api.config.add_route('admin-passwd', '/passwd')
        api.config.add_route('admin-asset', '/assets/{page_name:.*}')
        api.config.add_route('admin-doc', '/docs/{page_name:.*}', accept="text/html")
        api.config.add_route('admin-page', '/{page_name}', accept="text/html")
        api.config.add_route('admin-object', '/{page_name}/{object_name:.*}', accept="text/html")

        api.config.add_view(self.admin_passwd, route_name='admin-passwd')
        api.config.add_view(self.admin_asset, route_name='admin-asset')
        api.config.add_view(self.admin_doc, route_name='admin-doc')
        api.config.add_view(self.admin, route_name='admin-page')
        api.config.add_view(self.admin, route_name='admin-object')

        api.config.add_view(context='pyramid.exceptions.NotFound',
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
            header=None,
            footer=None,
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

                # Add prefix and postfix.
                if header is not None:
                    raw_page_data = "<%%include file=\"/%s\"/>\n%s" % \
                        (header, raw_page_data)
                if footer is not None:
                    raw_page_data = "%s\n<%%include file=\"/%s\"/>\n" % \
                        (raw_page_data, footer)

                # Convert markdown if necessary.
                if page_name.endswith(".md"):
                    raw_template_data = markdown.markdown(raw_page_data, extensions=['toc'])
                else:
                    raw_template_data = raw_page_data

                # Render if necessary.
                if render_template:
                    lookup = TemplateLookup(directories=include_dirs)
                    template = Template(raw_template_data, lookup=lookup)
                    loggedin = authenticated_userid(request) is not None
                    template_args = {
                        "object": object_name,
                        "user": loggedin and 'admin' or '',
                        "loggedin": loggedin,
                    }
                    template_args.update(kwargs)
                    page_data = template.render(**template_args)
                else:
                    page_data = raw_template_data

                # Check for supported types.
                ext = page_name.split('.')[-1]
                headers = {
                    "Content-type": MIMEMAP.get(ext, "text/plain")
                }
            except Exception:
                page_data = exceptions.html_error_template().render()
                headers = {
                    "Content-type": "text/html"
                }

            return Response(body=page_data, headers=headers)
        else:
            return Response(status=403)

    @connected
    @authorized(forbidden_view='self.admin_login')
    def admin(self, context, request):
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

    def admin_doc(self, context, request):
        """
        Render a documentation page.
        """
        return self._serve(
            context,
            request,
            base_dir=os.path.join(
                os.path.dirname(__file__),
                'admin',
                'docs'),
            include_dirs=[
                os.path.join(
                    os.path.dirname(__file__),
                    'admin',
                    'docs'),
                os.path.join(
                    os.path.dirname(__file__),
                    'admin',
                    'include'),
            ],
            header="docheader.html",
            footer="docfooter.html",
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
            response = self.api.login(context, request)
            return HTTPFound(location=came_from, headers=response.headers)
        except NotImplementedError:
            # Credentials not submitted or incorrect, render login page.
            if self.api._req_get_auth_key(request) != None:
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
        response = self.api.logout(context, request)
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
            self.api.zkobj.auth_hash = self.api._create_admin_auth_token(auth_key)

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
