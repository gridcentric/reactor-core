<h1>Docker</h1>

[TOC]

Docker can be used to run containers across different managers. Each manager
runs their own docker instances, but the cluster will co-ordinate and schedule
instances appropriately.

## Manager Options

* slots

The available docker scheduling slots on this host.

## Endpoint Options

* slots

The number of scheduled slots required.

* image

The docker image name.

* command

The docker command to run in the given image.

* user

The user to use for running the command.

* environment

The environment for the command.

* mem_limit

The memory limit for the container.

* dns

The DNS server for the container.

* hostname

The hostname of the container.
