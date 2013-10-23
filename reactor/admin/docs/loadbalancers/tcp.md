<h1>Managed TCP</h1>

[TOC]

Managed TCP provides TCP load balancing with more control. It allows you to
specify exclusivity on the backends, reconnects and control allowed subnets.

## Supported URL schemes

* tcp://{:port}

## Endpoint Options

* exclusive

Whether or not endpoint instances are exclusive. If instances are exclusive,
only one connection will be allowed through at a time. Connections will be held
in a queue until more instances are free or new instances are created.

* reconnect

If reconnect is set, when a client disconnects instances are not immediately
available for new clients. The system will wait for the reconnect timeout to
pass until new clients can connect. If the original client reconnects in this
period, they will be reconnected to the original instance.

* client_subnets

Only allow connections from the given subnets.

## Example

See RDP.
