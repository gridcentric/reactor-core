import threading
import logging
import json
import os
import uuid

from pyramid.response import Response
from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions

from reactor.api import ReactorApi
from reactor.api import connected
from reactor.api import authorized
from reactor.api import authorized_admin_only
from reactor.api import get_auth_key

from reactor.server.manager import ReactorScaleManager
import reactor.server.ips as ips
import reactor.server.config as config

class ServerApi(ReactorApi):
    def __init__(self, zk_servers):
        self.manager_running = False
        ReactorApi.__init__(self, zk_servers)

        self.config.add_route('api-servers', '/api_servers')
        self.config.add_view(self.set_api_servers, route_name='api-servers')

        self.config.add_route('admin-home',   '/admin/')
        self.config.add_route('admin-page',   '/admin/{page_name}')
        self.config.add_route('admin-object', '/admin/{page_name}/{object_name:.*}')
        self.config.add_view(self.admin, route_name='admin-home')
        self.config.add_view(self.admin, route_name='admin-page')
        self.config.add_view(self.admin, route_name='admin-object')

        # Check the endpoint.
        self.check(zk_servers)

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
    def admin(self, context, request):
        """
        Render a page from the admin directory and write it back.
        """
        if request.method == 'GET':
            # Read the page_name from the request.
            page_name = request.matchdict.get('page_name', 'index')
            object_name = request.matchdict.get('object_name', '')

            if page_name == 'lib':
                is_lib = True
                page_name = os.path.join(page_name, object_name)
            else:
                is_lib = False
                if object_name and page_name.endswith('s'):
                    page_name = page_name[:-1]
                if page_name.find('.') < 0:
                    page_name += '.html'

            # Check that the file exists.
            filename = os.path.join(os.path.dirname(__file__), 'admin', page_name)
            if not(os.path.exists(filename)):
                return Response(status=404)

            if is_lib:
                # Just open the page and write it out.
                page_data = open(filename).read()
            else:
                # Process the request with all params.
                # This allows us to generate pages that include
                # arbitrary parameters (for convenience).
                lookup_path = os.path.join(os.path.dirname(__file__), 'admin', 'include')
                lookup = TemplateLookup(directories=[lookup_path])
                template = Template(filename=filename, lookup=lookup)
                auth_key = get_auth_key(request)
                kwargs = {}
                kwargs.update(request.params.items())
                kwargs["auth_key"] = auth_key
                kwargs["uuid"]     = str(uuid.uuid4())
                kwargs["object"]   = object_name

                try:
                    page_data = template.render(**kwargs)
                except:
                    page_data = exceptions.html_error_template().render()

            # Check for supported types.
            ext = page_name.split('.')[-1]
            mimemap = { "js"   : "application/json",
                        "png"  : "image/png",
                        "gif"  : "image/gif",
                        "html" : "text/html",
                        "css"  : "text/css" }

            return Response(body=page_data,
                            headers={"Content-type" : mimemap[ext]})
        else:
            return Response(status=403)


    def start_manager(self, zk_servers):
        zk_servers.sort()
        self.zk_servers.sort()
        if self.zk_servers != zk_servers:
            self.stop_manager()

        if not(self.manager_running):
            self.manager = ReactorScaleManager(zk_servers)
            self.manager_thread = threading.Thread(target=self.manager.run)
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
