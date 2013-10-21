<h1>HAProxy</h1>

[TOC]

HAProxy provides reliable HTTP load balancing, as well as raw TCP load
balancing (useful for SSL passthrough). It also monitors instances and can be
used to automatically detect errors based on the `error_marks` configuration
parameter.

Note that simultaneous use of HAProxy and Nginx endpoints on the same ports is
not supported.

## Supported URL schemes

* http://{host[:port]}

Point requests for the given virtual server and path to the endpoint.

* http://{[:port]}

Point all unmatched connections (without a matching virtual server) to the endpoint.

* tcp://{:port}

Provide high-performance TCP load balancing. This is useful to provide your own
SSL termination, or other TCP-based services.

## Manager Options

* pid_file

The pid file for the HAProxy daemon.

* config_file

The configuration file for the HAProxy daemon.

* stats_path

The path to the stats socket for the HAProxy daemon.

* stats_mode

The mode to create the stats socket (permissions).

* global_opts

Global options used in generating the HAProxy configuration.

* maxconn

The maximum connections handled by HAProxy simultaneously.

* clitimeout

The default client timeout for contacting backends.

## Endpoint Options

* balance

The loadbalancing mode (for exapmle, roundrobin).

* sticky

Whether client sessions should be sticky.

* check_url

When using HTTP, this URL should be set to enable health checks.

* errorloc

The location on backends to fetch on an error, accessed `errorloc`/`code`.

* contimeout
* srvtimeout

Generic connection and server timeouts.

## Example

Suppose you want to enable a web application at `www.foo.com`. You can set the
endpoint URL to `http://www.foo.com`. You should then set the IP addresses for
your service to the IP addresses of the Reactor instances.
