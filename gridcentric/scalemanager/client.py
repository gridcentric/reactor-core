
from gridcentric.scalemanager.zookeeper.connection import ZookeeperConnection

class ScaleManagerClient(object):
    
    def __init__(self, zk_servers):
        self.zk_conn = ZookeeperConnection(zk_servers)
    
    def list_managed_services(self):
        return self.zk_conn.list_children("/gridcentric/scalemanager/service")
    
    def manage_service(self, service_name, config):
        self.zk_conn.write("/gridcentric/scalemanager/service/%s" %(service_name), config)
    
    def unmanage_service(self, service_name):
        self.zk_conn.delete("/gridcentric/scalemanager/service/%s" % (service_name))
        
    def update_service(self, service_name, config):
        self.zk_conn.write("/gridcentric/scalemanager/service/%s" % (service_name), config)
    
    def get_service_config(self, service_name):
        return self.zk_conn.read("/gridcentric/scalemanager/service/%s" % (service_name))