from pyramid.config import Configurator
from pyramid.response import Response

from gridcentric.scalemanager.client import ScaleManagerClient


class ScaleManagerApi:
    
    def __init__(self, zk_servers):
        self.client = ScaleManagerClient(zk_servers)
        self.config = Configurator()
        
        self.config.add_route('new-ip', '/gridcentric/scalemanager/new-ip/{ipaddress}')
        self.config.add_view(self.new_ip_address, route_name='new-ip')

    def get_wsgi_app(self):
        return self.config.make_wsgi_app()
    
    def new_ip_address(self, context, request):
        self.client.record_new_ipaddress(request.matchdict['ipaddress'])
        return Response()
    