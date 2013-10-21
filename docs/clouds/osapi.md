<h1>OpenStack</h1>

[TOC]

The OpenStack cloud connection is used for boot instances on standard OpenStack
clouds.

## Common Options

Both OpenStack+VMS and OpenStack share these options.

* auth_url

The authentication URL for the OpenStack cloud (OS_AUTH_URL).

* username

The authentication username (OS_USERNAME).

* password

The authentication password (OS_PASSWORD).

* tenant_name

The tenant name for new instances (OS_TENANT_NAME).

* region_name

The region name for new instances (OS_REGION_NAME).

* list_rate_limit

To avoid hitting API rate limits, only update at most this often.

* security_groups

List of security groups for new instances.

* availability_zone

Availability zone for new instances.

## Endpoint Options

In addition to the above, the following are available for booted instances.

* instance_name

The name for new instances.

* flavor_id

The flavor for new instances.

* image_id

The image for new instances.

* key_name

The key_name for cloud-init and key injection (if supported).
