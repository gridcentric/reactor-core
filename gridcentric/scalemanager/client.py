
from gridcentric.scalemanager.zookeeper.connection import ZookeeperConnection
import gridcentric.scalemanager.zookeeper.paths as paths 

class ScaleManagerClient(object):
    
    def __init__(self, zk_servers):
        self.zk_conn = ZookeeperConnection(zk_servers)
    
    def list_managed_services(self):
        return self.zk_conn.list_children(paths.services)
    
    def manage_service(self, service_name, config):
        self.zk_conn.write(paths.service(service_name), config)
    
    def unmanage_service(self, service_name):
        self.zk_conn.delete(paths.service(service_name))
        
    def update_service(self, service_name, config):
        self.zk_conn.write(paths.service(service_name), config)
    
    def get_service_config(self, service_name):
        return self.zk_conn.read(paths.service(service_name))
    
    def record_new_ipaddress(self, ip_address):
        self.zk_conn.write(paths.new_ip(ip_address), "")