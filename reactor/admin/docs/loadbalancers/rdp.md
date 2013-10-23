<h1>RDP</h1>

[TOC]

The RDP load balancer allows you to provide RDP services to a pool of Windows
instances. When using OpenStack+VMS as your cloud provided, these VMs can be
Active Directory-enabled and provide the basis for a VDI installation.

## Supported URL schemes

In *addition* to the options below, all options from Managed TCP above are
available as RDP options.

* rdp://{[:port]}

## Endpoint Options

* domain

The Windows Active Directory (AD) domain.

* username

An administrator username for the AD domain.

* password

The password for the username above.

* orgunit

The organizational unit to create new machines in.

* template

The template for new machine names.

* host

The AD host, if it cannot be looked up automatically via DNS.

## Example

To provide an RDP service, fill in all the options for the creation of Windows
machine accounts. Then point your RDP connections at the IP for the Reactor
instance.
