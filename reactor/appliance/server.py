import logging

from paste.httpserver import serve

import reactor.log as log
import reactor.appliance.config as config

from reactor.appliance.api import ApplianceApi

def main():
    log.configure(logging.DEBUG, "/var/log/reactor.log")

    try:
        zk_servers = config.read_config()
    except:
        zk_servers = []
    if len(zk_servers) == 0:
        zk_servers = ["localhost"]

    app = ApplianceApi(zk_servers)
    serve(app.get_wsgi_app(), host='0.0.0.0')
