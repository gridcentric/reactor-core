import logging

from paste.httpserver import serve

import gridcentric.reactor.log as log
import gridcentric.reactor.config as config

from gridcentric.reactor.api import ReactorApi

def main():
    log.configure(logging.DEBUG, "/var/log/reactor.log")

    try:
        zk_servers = config.read_config()
    except:
        zk_servers = []
    if len(zk_servers) == 0:
        zk_servers = ["localhost"]

    app = ReactorApi(zk_servers)
    serve(app.get_wsgi_app(), host='0.0.0.0')
