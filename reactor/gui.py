import os
import json

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
        api.config.add_route('admin-page', '/{page_name}', accept="text/html")
        api.config.add_route('admin-asset', '/assets/{object_name:.*}')
        api.config.add_route('admin-object', '/{page_name}/{object_name:.*}', accept="text/html")

        api.config.add_view(self.admin_passwd, route_name='admin-passwd')
        api.config.add_view(self.admin_asset, route_name='admin-asset')
        api.config.add_view(self.admin, route_name='admin-page')
        api.config.add_view(self.admin, route_name='admin-object')
        api.config.add_view(context='pyramid.exceptions.NotFound',
            view='pyramid.view.append_slash_notfound_view')

    @connected
    def manager_info(self, context, request):
        return Response(body=json.dumps(ManagerConfig().spec()))

    @connected
    def endpoint_info(self, context, request):
        return Response(body=json.dumps(EndpointConfig().spec()))

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
        message = ''

        try:
            # See if the login form was submitted.
            response = self.api.login(context, request)
            return HTTPFound(location=came_from, headers=response.headers)
        except NotImplementedError:
            # Credentials not submitted or incorrect, render login page.
            filename = os.path.join(os.path.dirname(__file__), 'admin', 'login.html')
            lookup_path = os.path.join(os.path.dirname(__file__), 'admin', 'include')
            lookup = TemplateLookup(directories=[lookup_path])
            template = Template(filename=filename, lookup=lookup)
            if self.api._req_get_auth_key(request) != None:
                message = "Invalid credentials."
            else:
                message = ""
            kwargs = {
                'message' : message,
                'url' : route_url('admin-login', request),
                'came_from' : came_from,
                'user' : '',
                'loggedin' : False
            }
            body = template.render(**kwargs)
            return Response(body=body)

    def admin_logout(self, context, request):
        """
        Logs the admin user out.
        """
        response = self.api.logout(context, request)
        return HTTPFound(location=route_url('admin-login', request), headers=response.headers)

    @connected
    @authorized(forbidden_view='self.admin_login')
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
            except Exception:
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
