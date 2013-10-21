<h1>API Reference</h1>

[TOC]

# Basics

## Schema
All data is in [JSON](http://www.json.org/) format.

## Reactor API version
The Reactor API version is obtained by performing an HTTP `GET` to the root path of the Reactor API:

    $ curl -i -X GET http://api.example.com
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 18
    Connection: keep-alive
    
    {"version": "1.0"}

## API access
The Reactor API is accessed via HTTP on port 80 of the Reactor virtual appliance. The general format for URLs is:

    http://api.<domain>/v<version>/<path>

for example:

    $ curl -i -X GET http://api.example.com/v1.0/domain
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 25
    Connection: keep-alive
    Vary: Accept-Encoding
    
    {"domain": "example.com"}

# Management Paths
## /auth_key
### Setting the Reactor API password
The Reactor API password is set via a `POST` to the `/auth_key` path:

    $ curl -i -X POST -H 'Content-type: application/json' -d '{"auth_key" : "<password>"}' \
        http://api.example.com/v1.0/auth_key
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

The required parameters are:

* `auth_key` - The new Reactor API password.

Note that if the Reactor API password has been set, the HTTP header `X-Auth-Key` is required for all further accesses (including re-setting the API password).

## /domain
### Getting the Reactor domain
The Reactor domain is retrieved via a `GET` to the `/domain` path:

    $ curl -i -X GET -H 'X-Auth-Key: password' http://api.example.com/v1.0/domain
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 25
    Connection: keep-alive
    Vary: Accept-Encoding
    
    {"domain": "example.com"}

### Setting the Reactor domain
The Reactor domain is set via a `POST` to the `/domain` path:

    $ curl -i -X POST -H 'X-Auth-Key: <password>' -H 'Content-type: application/json' \
        -d '{"domain" : "example.net"}' \
        http://api.example.com/v1.0/domain
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

The required parameters are:

* `domain` - The new Reactor API domain.

## /config
### Getting the Reactor configuration
The Reactor configuration is retrieved via a `GET` to the `/config` path:

    $ curl -i -X GET -H 'X-Auth-Key: <password>' http://api.example.com/v1.0/config
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 70
    Connection: keep-alive

    {"config": <configuration data>}

For information on the configuration data format see the [User Guide](user-guide#configuring_the_load_balancing_policy).

### Setting the Reactor configuration
The Reactor configuration is set via a `POST` to the `/config` path:

    $ curl -i -X POST -H 'X-Auth-Key: <password>' -H 'Content-type: application/json' \
        -d '{"config" : <configuration data>}' http://api.example.com/v1.0/config
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

The required parameters are:

* `config` - The Reactor configuration.

For information on the configuration data format see the [User Guide](user-guide#configuring_the_load_balancing_policy).

## /managers
### Getting the list of current Reactors
The list of Reactor virtual appliances that have been added to the Reactor system is retrieved via a `GET` to the `/managers` path:

    $ curl -i -X GET -H 'X-Auth-Key: <password>' http://api.example.com/v1.0/managers
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 49
    Connection: keep-alive
    Vary: Accept-Encoding

    {"managers" : ["192.168.0.100", "192.168.0.101"]}

### Adding a new Reactor instance
A new Reactor instance is added to the system via a `POST` to the `/managers` path of an already-configured Reactor:

    $ curl -i -X POST -H 'X-Auth-Key: <password>' -H 'Content-type: application/json' \
        -d '{"manager" : "192.168.0.102"} \
        http://api.example.com/v1.0/managers
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

The required parameters are:

* `manager` - The IP address of the Reactor instance to add to the system.

### Removing a Reactor instance
A Reactor instance is removed from the system via a `DELETE` to the `/managers/<ip address>` path:

    $ curl -i -X DELETE -H 'X-Auth-Key: <password>' http://api.example.com/v1.0/managers/192.168.0.102
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

Note that this operation will fail if only one Reactor instance has been added to the system.

## /endpoints
### Adding an endpoint
A new endpoint is added to the system via a `POST` to the `/endpoints/<endpoint name>` path:

    $ curl -i -X POST -H 'X-Auth-Key: <password>' -H 'Content-type: application/json' \
        -d '{"config" : <configuration data>} \
        http://api.example.com/v1.0/endpoints/www-production
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

The required parameters are:

* `config` - The configuration data for the endpoint.

For information on the configuration data format see the [User Guide](user-guide#creating_an_endpoint).

### Updating an endpoint's configuration
An endpoint's configuration is updated via a `POST` to the `/endpoints/<endpoint name>` path:

    $ curl -i -X POST -H 'X-Auth-Key: <password>' -H 'Content-type: application/json' \
        -d '{"config" : <configuration data>} \
        http://api.example.com/v1.0/endpoints/www-production
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

The required parameters are:

* `config` - The configuration data for the endpoint.

Note that updating an endpoint causes the configuration for that endpoint to be overwritten.

For information on the configuration data format see the [User Guide](user-guide#creating_an_endpoint).

### Removing an endpoint
An endpoint is removed via a `DELETE` to the `/endpoints/<endpoint name>` path:

    $ curl -i -X DELETE -H 'X-Auth-Key: <password>' http://api.example.com/v1.0/endpoints/www-production
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

### Getting the state of an endpoint
The state of an endpoint is retrieved via a `GET` to the `/endpoints/<endpoint name>/state` path:

    $ curl -i -X GET -H 'X-Auth-Key: <password>' http://api.example.com/v1.0/endpoints/www-production/state
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 49
    Connection: keep-alive
    Vary: Accept-Encoding

    {"state" : "RUNNING"}

The returned `state` field is either:

* `RUNNING` - the endpoint is running.
* `STOPPED` - the endpoint is stopped.

### Starting an endpoint
An endpoint is started via a `POST` to the `/endpoints/<endpoint name>/state` path:

    $ curl -i -X POST -H 'X-Auth-Key: <password>' -H 'Content-type: application/json' \
        -d '{"action" : "start"} \
        http://api.example.com/v1.0/endpoints/www-production/state
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

The required parameters are:

* `action` - If starting the endpoint, this field should be set to `start`.

### Stopping an endpoint
An endpoint is stopped via a `POST` to the `/endpoints/<endpoint name>/state` path:

    $ curl -i -X POST -H 'X-Auth-Key: <password>' -H 'Content-type: application/json' \
        -d '{"action" : "stop"} \
        http://api.example.com/v1.0/endpoints/www-production/state
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

The required parameters are:

* `action` - If stopping the endpoint, this field should be set to `stop`.

### Getting endpoint instance IPs
The list of currently registered endpoint instance IP addresses is retrieved via a `GET` to the `/endpoints/<endpoint name>/ips` path:

    $ curl -i -X GET -H 'X-Auth-Key: <password>' http://api.example.com/v1.0/www-production/ips
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 67
    Connection: keep-alive
    Vary: Accept-Encoding

    {"ips" : ["192.168.0.201", "192.168.0.202", "192.168.0.203"]}

### Getting endpoint metrics
Current endpoint metrics (e.g. number of active connections, etc) are retrieved via a `GET` to the `endpoints/<endpoint name>/metrics` path:

    $ curl -i -X GET -H 'X-Auth-Key: <password>' http://api.example.com/v1.0/www-production/metrics
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 38
    Connection: keep-alive
    Vary: Accept-Encoding

    {"active" : "20.1", "response" : "50"}

### Posting global endpoint metrics
Global metrics are reported to Reactor via a `POST` to the `endpoints/<endpoint name>/metrics` path:

    $ curl -i -X POST -H 'X-Auth-Key: <password>' -H 'Content-type: application/json' \
        -d '{"<metric name>" : <metric value>} \
        http://api.example.com/v1.0/endpoints/www-production/metrics
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

Global metrics reported in this manner are not accumulated - i.e. they are not weighted, summed, or tracked over time. Instead, any previously held value for the metric is overwritten with the new value. Global metrics are /scaled by the number of endpoint instances/ before applying scaling rules.

# Instance Paths
## /register
### Registering a new application instance
A new application instance (i.e., a new virtual machine that has been created by Reactor) needs to register with the Reactor system before Reactor will start directing traffic to it.

Registration is performed via a `POST` to the `/register` path:

    $ curl -i -X POST -H http://api.example.com/v1.0/register
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

Note that an authentication key is not required; Reactor will ignore registration requests that do not originate from addresses of virtual machine instances created by Reactor.

## /metrics
### Reporting instance-specific metrics
Application metrics are reported via a `POST` to the `/metrics` path:

    curl -i -X POST -H 'Content-type: application/json' \
        -d '{ "<metric name>" : [<metric weight>, <metric value>] }' \
        http://api.example.com/v1.0/metrics
    HTTP/1.1 200 OK
    Content-Type: application/json; charset=UTF-8
    Content-Length: 0
    Connection: keep-alive

The metric calculation takes the sum of all reported metric values and divides it by the sum of all metric weights. Metrics reported with a weight of zero are discarded.

All instances should, at a minimum, report an `active` metric, that should be non-zero when the instance is actively processing (e.g. handling connections) and zero when the instance is idle. Doing so will assist Reactor in making scale-down decisions.

Note that an authentication key is not required; Reactor will ignore registration requests that do not originate from addresses of virtual machine instances created by Reactor.
