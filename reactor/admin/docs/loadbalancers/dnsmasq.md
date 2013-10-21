<h1>Dnsmasq</h1>

[TOC]

Dnsmasq provides basic DNS support. It exposes all endpoint instances under a
given DNS name. You need to have the Reactor instance as the nameserver for the
given namespace, and create appropriate `CNAME` DNS records for your service.

## Supported URL schemes

* dns://{name}

The {name} is the DNS name. For example, if the name is `service.example.com`,
then `example.com` will need to have `NS` records pointing to your Reactor
instances. This will resolve `service.example.com` to all relevant instances.

## Manager Options

* pid_file

The pid file for the Dnsmasq service.

* config_path

The config path for the Dnsmasq service.

* hosts_path

The path to generate the Reactor hosts file.

## Example

Suppose you want to enable a web application at `www.foo.com` and have the
appropriate `NS` records for `example.com`. You can create an endpoint
`foo-com` with the URL `dns://foo.example.com`. Then, add a `CNAME` record to
`foo.com` for `www` that points to `foo.example.com`.
