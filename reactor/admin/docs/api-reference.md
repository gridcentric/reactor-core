<h1>API Reference</h1>

[TOC]

# Basics

## Schema

All data is in [JSON](http://www.json.org/) format.

## API Access

The Reactor API is available by default on port 8080. The default endpoints
include one that makes this available on port 80 (if nginx is running) but you
can choose to expose the API in any way you want.

In this documentation, we will use `curl` to access the API. You may of course,
use any tool or language that you like.

## Accept and Content types

Reactor may behave differently depending on the `Accept` headers. Be sure to
use `Accept: application/json` for programmatic API access.

All data posted to the API should include an approprate `Content-Type` header,
with the value `application/json`.

## API Version

The Reactor API version is obtained by performing an HTTP `GET` to the root path of the Reactor API.

<pre class="alert alert-success">
GET /
</pre>

Data: none.

Result: {"version": *api-version*}

Example:

    curl -i -H 'Accept: application/json' -X GET http://localhost:8000

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 18

{"version": "1.1"}
</pre>

Reactor uses [semantic versioning](http://semver.org/) for the API.

All calls for version `v1.1` of the API are available via the path `/v1.1/`.

## Authentication

If you've set an authentication key for Reactor, you must pass this as the
header `X-Auth-Key` or as a parameter `auth_key`. We highly recommended
requiring API access through SSL when securing Reactor. (This is possible using
the default apihttps endpoint, but you should provide a signed SSL key and
certificate).

For example, if you don't provide the authentication key.

    curl -i -H 'Accept: application/json' -X GET http://localhost:8080/v1.1/endpoints

<pre class="alert alert-error">
HTTP/1.0 401 Unauthorized
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 12
unauthorized
</pre>

Then, upon providing the key.

    curl -i -H 'Accept: application/json' -H 'X-Auth-Key: bar' -X GET http://localhost:8080/v1.1/endpoints

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 23

{"endpoints": []}
</pre>

Alternately, providing the key via a query parameter.

    curl -i -H 'Accept: application/json' -X GET http://localhost:8080/v1.1/endpoints?auth_key=bar

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 23

{"endpoints": []}
</pre>

# Global Settings

## Set Authentication Key

<pre class="alert alert-success">
POST /v1.1/auth_key
</pre>

Data: {"auth_key": *authentication-key*}

Result: none.

Example:

    curl -i --data '{"auth_key": "bar"}' -H 'Content-Type: application/json' -H 'Accept: application/json' -X POST http://localhost:8080/v1.1/auth_key

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 0
</pre>

## Get URL

<pre class="alert alert-success">
GET /v1.1/url
</pre>

Data: none.

Result: {"url": *url*}

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/url

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 25

{"url": "http://example.com"}
</pre>

## Set URL

<pre class="alert alert-success">
POST /v1.1/url
</pre>

Data: {"url": *url*}

Result: none.

Example:

    curl -i --data '{"url": "http://example.com"}' -H "Content-Type: application/json" -H "Accept: application/json" -X POST http://localhost:8080/v1.1/url

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 0
</pre>

## Get Global Info

These global statistics provide a quick snapshot into the state of the system.

<pre class="alert alert-success">
GET /v1.1/info
</pre>

Data: none.

Result: {"active": *active*, "instances": *instances*, "managers": *managers*, "endpoints": {*state*: *state-count*, ...}}

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/info

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 73

{"active": 0, "instances": 0, "endpoints": {"STOPPED": 1}, "managers": 0}
</pre>

# IP Registration

## Register IP

<pre class="alert alert-success">
POST /v1.1/register/{ip}
POST /v1.1/register
</pre>

Data: none.

Result: none.

Example:

    curl -i -H "Content-Type: application/json" -H "Accept: application/json" -X POST http://localhost:8080/v1.1/register/127.0.0.1

<pre class="alert alert-info">
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 0
</pre>

## Unregister IP

<pre class="alert alert-success">
POST /v1.1/unregister/{ip}
POST /v1.1/unregister
</pre>

Data: none.

Result: none.

Example:

    curl -i -H "Content-Type: application/json" -H "Accept: application/json" -X POST http://localhost:8080/v1.1/unregister/127.0.0.1

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 0
</pre>

# Managers

## List Managers

<pre class="alert alert-success">
GET /v1.1/managers
</pre>

Data: none.

Result: {"active": [*manager*, ...], "configured": [*manager*, ...]}

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/managers

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 100

{"active": {}, "configured": ["172.0.0.1", "10.0.2.15", "192.168.1.2", "10.0.3.1", "192.168.122.1"]}
</pre>

## Get Manager Configuration

<pre class="alert alert-success">
GET /v1.1/managers/{manager}
</pre>

Data: none.

Result: The full configuration along with *info* and *uuid*.

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/managers/127.0.0.1

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 28

{"info": null, "uuid": null}
</pre>

## Create or Set Manager Configuration

<pre class="alert alert-success">
POST /v1.1/managers/{manager}
</pre>

Data: The full configuration.

Result: none or validation errors.

Example:

    curl -i --data '{}' -H "Content-Type: application/json" -H "Accept: application/json" -X POST http://localhost:8080/v1.1/managers/127.0.0.1

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 0
</pre>

## Delete Manager

<pre class="alert alert-success">
DELETE /v1.1/managers/{manager}
</pre>

Data: none.

Result: none.

Example:

    curl -i -H "Accept: application/json" -X DELETE http://localhost:8080/v1.1/managers/127.0.0.1

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 0
</pre>

## Get Manager Log

<pre class="alert alert-success">
GET /v1.1/managers/{manager}/log[?since=<since>]
</pre>

Data: none.

Result: [[*timestamp*, *severity*, *message*], ...]

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/managers/127.0.0.1/log

<pre class="alert alert-info">
TTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 2

[]
</pre>

# Endpoints

## List Endpoints

<pre class="alert alert-success">
GET /v1.1/endpoints
</pre>

Data: none.

Result: [*endpoint*, ...]

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/endpoints

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 8

["demo"]
</pre>

## Get Endpoint Configuration

<pre class="alert alert-success">
GET /v1.1/endpoints/{endpoint}
</pre>

Data: none.

Result: The full configuration.

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/endpoints/demo

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 3207

{...}
</pre>

## Create or Set Endpoint Configuration

<pre class="alert alert-success">
POST /v1.1/endpoints/{endpoint}
</pre>

Data: The full configuration.

Result: none or validation errors.

Example:

    curl -i --data '{}' -H "Content-Type: application/json" -H "Accept: application/json" -X POST http://localhost:8080/v1.1/endpoints/demo

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 0
</pre>

## Delete Endpoint

<pre class="alert alert-success">
DELETE /v1.1/endpoints/{endpoint}
</pre>

Data: none.

Result: none.

Example:

    curl -i -H "Accept: application/json" -X DELETE http://localhost:8080/v1.1/endpoints/demo

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 0
</pre>

## List Endpoint IPs

<pre class="alert alert-success">
GET /v1.1/endpoints/{endpoint}/ips
GET /v1.1/endpoint/ips
</pre>

Data: none.

Result: [*ip*, ...]

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/endpoints/demo/ips

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 2

[]
</pre>

## Get Endpoint Log

<pre class="alert alert-success">
GET /v1.1/endpoints/{endpoint}/log[?since=<since>]
GET /v1.1/endpoint/log[?since=<since>]
</pre>

Data: none.

Result: [*log-message*, ...]

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/endpoints/demo/log

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 2

[]
</pre>

## Get Endpoint Metics

<pre class="alert alert-success">
GET /v1.1/endpoints/{endpoint}/metrics
GET /v1.1/endpoint/metrics
</pre>

Data: none.

Result: {*metric*: *value*, ...}

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/endpoints/demo/metrics

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 2

{}
</pre>

## Get Endpoint IP Metrics

<pre class="alert alert-success">
GET /v1.1/endpoints/{endpoint}/metrics/{ip}
GET /v1.1/endpoint/metrics/{ip}
</pre>

Data: none.

Result: {*metric*: [*weight*, *value*], ...}

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/endpoints/demo/metrics/127.0.0.1

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 2

{}
</pre>

## Set Endpoint IP Metrics

<pre class="alert alert-success">
POST /v1.1/endpoints/{endpoint}/metrics/{ip}
POST /v1.1/endpoint/metrics/{ip}
POST /v1.1/endpoint/metrics
</pre>

Data: {*metric*: [*weight*, *value*], ...}

Result: none.

Example:

    curl -i --data '{"metric": [1.0, 7.2]}' -H "Content-Type: application/json" -H "Accept: application/json" -X POST http://localhost:8080/v1.1/endpoints/demo/metrics/127.0.0.1

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 0
</pre>

## Get Endpoint State

<pre class="alert alert-success">
GET /v1.1/endpoints/{endpoint}/state
GET /v1.1/endpoint/state
</pre>

Data: none.

Result: {"state": <endpoint-state>, "active": [<active-backend>, ...], "manager": <manager-uuid>}

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/endpoints/demo/state

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 50

{"active": [], "state": "PAUSED", "manager": null}
</pre>

## List Endpoint Sessions

<pre class="alert alert-success">
GET /v1.1/endpoints/{endpoint}/sessions
GET /v1.1/endpoint/sessions
</pre>

Data: none.

Result: {*client*:*port*: *backend*:*port*, ...}

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/endpoints/demo/sessions

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 2

{}
</pre>

## Query Endpoint Session

<pre class="alert alert-success">
GET /v1.1/endpoints/{endpoint}/sessions/{session}
GET /v1.1/endpoint/sessions/{session}
</pre>

Data: none.

Result: *backend*:*port*

Example:

    curl -i -H "Accept: application/json" -X GET http://localhost:8080/v1.1/endpoints/demo/sessions/127.0.0.1:38743

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 4

null
</pre>

## Drop Endpoint Session

<pre class="alert alert-success">
DELETE /v1.1/endpoints/{endpoint}/sessions/{session}
DELETE /v1.1/endpoint/sessions/{session}
</pre>

Data: none.

Result: none.

Example:

    curl -i -H "Accept: application/json" -X DELETE http://localhost:8080/v1.1/endpoints/demo/sessions/127.0.0.1:38273

<pre class="alert alert-info">
HTTP/1.0 200 OK
Server: PasteWSGIServer/0.5 Python/2.7.3
Content-Type: text/html; charset=UTF-8
Content-Length: 0
</pre>
