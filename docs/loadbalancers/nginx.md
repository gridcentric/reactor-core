<h1>Nginx</h1>

[TOC]

Nginx provides high-throughput HTTP loadbalancing. Unlike many other HTTP
loadbalancers, it also provides SSL termination.

Note that simultaneous use of HAProxy and Nginx endpoints on the same ports is
not supported.

## Supported URL schemes

* http://{host[:port][/path]}
* https://{host[:port][/path]}

Point requests for the given virtual server and path to the endpoint.

* http://{[:port]}
* https://{[:port]}

Point all unmatched connections (without a matching virtual server) to the endpoint.

## Manager Options

* pid_file

The pid file for the Nginx daemon.

* config_path

The config file for the Nginx daemon.

* site_path

The path for all nginx sites (often /etc/nginx/sites-enabled). Note that
Reactor can co-exist with existing sites.

## Endpoint Options

* sticky_sessions

Use cookies to route clients to the same backend.

* keepalive

Maintain connections with backends (improves performance).

* ssl

Enable SSL termination.

* ssl_certificate

The SSL certificate for SSL termination. If not provided, then a self-signed
certificate will be generated.

* ssl_key

The SSL private key for SSL termination.

* redirect

When no backends are available, a redirect URL to use.

## Example

Suppose you want to enable a web application at `www.foo.com`. You can set the
endpoint URL to `http://www.foo.com`. You should then set the IP addresses for
your service to the IP addresses of the Reactor instances.
