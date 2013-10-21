<h1>User Guide</h1>

[TOC]

# Architecting the Application

Two main decisions need to be made when architecting a Reactor-managed Application:

1. Which Reactor load balancing mechanism (if any) should be used?

1. Which scaling metrics should Reactor use to scale the application?

Insight into making these decisions is detailed below:

## Deciding Which Load Balancing Mechanism to Use
Reactor provides two built-in load balancing mechanisms: HTTP reverse-proxy load balancing (provided by [nginx](http://wiki.nginx.org)) and DNS round-robin load balancing (provided by [dnsmasq](http://www.thekelleys.org.uk/dnsmasq/doc.html)).

In some cases, the application itself provides load balancing capabilities. For example, a Hadoop cluster headnode is typically responsible for tasking out work to the slave nodes in its cluster. In these cases, Reactor does not perform any load balancing; instead, it performs scale management and makes instance information available to the application so that the application can make its own decisions about distributing load.

### HTTP-based
The HTTP-based load balancing mechanism is the preferred approach to load-balancing HTTP-based applications. It provides session "stickiness", and is optimized for delivery of HTTP-based applications. The HTTP-based load balancing mechanism is not appropriate for applications that are not based on HTTP.

The HTTP-based load balancing mechanism has the following configurable properties:

* `sticky_sessions` - This property indicates whether clients need to be sent to the same virtual machine instance over the course of their interaction with the application. For example, if the application makes use of PHP sessions, this property should be set to `true`. If it is not required for clients to be sent to the same virtual machine instance over the course of their intraction with the application, this property can be set to `false`. The default value is `true`.
* `keepalive` - This property specifies the amount of time, in seconds, that the load balancer should maintain a connection with the client. The default value is `0`.

### DNS-based
The DNS-based load balancing mechanism is used in cases where clients connect to a single application endpoint (e.g. a SIP proxy) that is not HTTP-based. The DNS-based load balancing mechanism works by returning different virtual machine instances in response to DNS queries on the hostname component of the endpoint URI. The DNS-baed load balancing mechanism should be used in cases where the HTTP-based load balancing mechanism is not applicable, but where the application endpoint can be addressed by a single URI.

The DNS-based load balancing mechanism has no configurable properties.

### Application-managed
In cases where the application manages the balancing of load among its resources, Reactor performs no load balancing functions; instead, it performs scale management and makes instance information available to the application so that the application can make its own decisions about distributing load.

## Using Metrics to Construct Scaling Policies
Application metrics are used to tell Reactor when to add or remove virtual machine instances from a Reactor-managed application.

### Built-in metrics
The following metrics are built-in for all applications:

* `instances` - The number virtual machine instances servicing the endpoint.
* `active` - The average number of active connections per virtual machine instance.

The following metrics are built-in for applications that use the HTTP-based load balancing mechanism:

* `response` - The average response time (in milliseconds) per HTTP transaction.
* `rate` - The number of HTTP transactions processed per virtual machine instance, per second.
* `bytes` - The amount of HTTP traffic processed (in bytes) per virtual machine instance, per second.

### Defining Scaling Rules
Scaling rules are defined in the form:

    [<min> (<|<=)] <metric> [(<|<=) <max>]

For example, the scaling rule:

    10 <= active <= 30

tells Reactor to keep the average number of active connections per instance between 10 and 30.

At least one minimum clause should be specified or else Reactor will never scale the number of virtual machine instances down. Likewise, at least one maximum clause should be specified or else Reactor will never scale the number of virtual machine instances up.

Multiple scaling rules can be specified by separating them with a comma. For example, the rule set:

    response < 300, 10 <= active <= 30

tells Reactor to maintain response times below 300ms, and keep the average number of active connections per instance between 10 and 30.

If two scaling rules conflict with each other, the rule that is earlier in the list takes precidence. For example, the rule set:

    2 <= instances, 10 <= active <= 30
    
tells Reactor to maintain at least two instances, and keep the number of active connections per instance between 10 and 30. If the average number of active connections drops below 10, Reactor will still keep two instances ready.

On the other hand, the rule set:

    10 <= active <= 30, response < 300

tells Reactor to keep the number of active connections per instance between 10 and 30 and maintain response times below 300ms. If the average number of active connections is already 10, Reactor will not increase the number of instances even if average response times rise above 300ms.

To construct a scaling policy where:

* We always maintain at least two instances and at most ten instances
* As long as the above holds, we maintain response times below 300ms
* As long as the above holds, we maintain active connections between 10 and 30

we would use the rule set:

    2 <= instances <= 10, response < 300, 10 <= active <= 30

### Custom metrics
Applications can also use custom metrics to define scaling policies. For example, a SIP application may be required to maintain a dropped call rate of less than 1%. This would be represented by a scaling rule such as:

    dropped_calls < 0.01

Each application instance would then report the number of calls it had dropped, along with a *weight*. The weight is used by Reactor to calculate the average value of the custom metric. In the SIP example, the weight would be the total number of calls processed by the instance in the same time period. For example, if an instance handled 1000 calls during a period of time and dropped eight of them, it would report the following to Reactor:

    { "dropped_calls" : [ 8, 1000 ] }

If this were the only instance in the system, Reactor would calculate an average `dropped_calls` rate of 0.008 and thus the above scaling rule is satisfied. If, however, an additional instance also reported to Reactor:

    { "dropped_calls" : [ 12 , 1000 ] }

then Reactor would calculate an average `dropped_calls` rate of 0.010 and scale up the number of instances in the system.

For more information on instance reporting see the [Reactor API Reference](api-reference.md).

# Deploying a Reactor System
## Reactor configuration
### Initial configuration
Initial configuration of a Reactor instance is performed using the `reactor setup` command:

    $ reactor setup --domain=<domain> <ip addr of reactor instance>

For example:

    $ reactor setup --domain=example.com 192.168.0.100
    Admin password for reactor is unset!
    Please enter a new admin password:
    Please re-enter new admin password:
    Password updated!
    Domain set to example.com
    Reactor API is accessable at api.example.com
    Add an entry in your DNS or hosts file to point 192.168.0.100 to api.example.com
     if you would like to access the API by hostname.
    Initial Reactor setup is complete.

From this point onward, Reactor must be accessable via the `api.<domain>` set, either via an entry in `/etc/hosts` or a DNS entry.

The domain can be reset by re-running the `reactor setup` command with the new domain.

### Adding an additional Reactor 
Additional Reactor instances can be added to an existing Reactor cluster using the `reactor add` command:

    $ reactor add --domain=<domain> <ip addr of reactor instance>

For example:

    $ reactor add --domain=example.com 192.168.0.101
    Please enter admin password for Reactor at api.example.com:
    Contacting Reactor at api.example.com...
    Adding 192.168.0.101 to Reactor cluster...
    Reactor added to api.example.com
    You may now add 192.168.0.101 to the DNS record for api.example.com

### Configuring the load balancing policy
The load balancing policy is set by pushing a configuration file to Reactor. The format for the configuration file is that defined in [RFC 822](http://tools.ietf.org/html/rfc822.html) (i.e. the format parsed by the Python [ConfigParser](http://docs.python.org/library/configparser.html) class). The configuration file has the following format:

    [loadbalancer]
    policy=(http|dns|none)
    sticky_sessions=(true|false)
    keepalive=<integer>

Note that the `sticky_sessions` and `keepalive` parameters are optional and are only used if `policy` is set to `http`.

The configuration file is pushed to Reactor using the `reactor config` command:

    $ reactor config --domain=<domain> <path to config file>

For example:

    $ reactor config --domain=example.com reactor.conf
    Please enter admin password for Reactor at api.example.com:
    Contacting Reactor at api.example.com...
    Configuring Reactor with configuration file "reactor.conf"...
    Reactor is now configured with load-balancer policy "http".

## Endpoint configuration
### Creating an endpoint
Endpoints are created by pushing a configuration file to Reactor. The configuration file has the following format:

    [endpoint]
    url=<URL of endpoint>
    
    [scaling]
    rules=<list of scaling rules>
    min_instances=<integer>
    max_instances=<integer>
    
    [nova-vms]
    instance_id=<VMS-enabled instance ID>
    authurl=<OpenStack API URL>
    user=<OpenStack username>
    apikey=<OpenStack password>
    project=<OpenStack project>

The parameters have the following meanings:

* General parameters:

  * `url` - The URL of the endpoint. Only required for using the `http` load balancer policy.

* Scaling parameters:
  * `rules` - The list of scaling rules used to scale the endpoint up and down.
  * `min_instances` - The absolute minimum number of instances to create, regardless of metrics and scaling rules.
  * `max_instances` - The absolute maximum number of instances to create, regardless of metrics and scaling rules.
* VMS parameters (OpenStack-specific):
  * `instance_id` - The VMS-enabled VM template to use for creating new instances.
  * `authurl` - The URL used to access the OpenStack API for the cloud this endpoint resides in.
  * `user` - The OpenStack username for the cloud this endpoint resides in.
  * `apikey` - The OpenStack password for the cloud this endpoint resides in.
  * `project` - The OpenStack project for the cloud this endpoint resides in.

The configuration file is pushed to Reactor using the `reactor endpoint-create` command:

    $ reactor endpoint-create --domain=<domain> <endpoint name> <path to config file>

For example:

    $ reactor endpoint-create --domain=example.com www-production www-production.conf
    Please enter admin password for Reactor at api.example.com:
    Contacting Reactor at api.example.com...
    Configuring Reactor endpoint "www-production" with configuration file "www-production.conf"...
    Reactor endpoint "www-production" is now configured.

### Starting an endpoint
Endpoints are started using the `reactor endpoint-start` command:

    $ reactor endpoint-start --domain=<domain> <endpoint name>

For example:

    $ reactor endpoint-start --domain=example.com www-production
    Please enter admin password for Reactor at api.example.com:
    Contacting Reactor at api.example.com...
    Starting Reactor endpoint "www-production".
    Using load-balancing policy "http".
    Waiting for 1 initial instance to come online...
    Reactor endpoint "www-production" is now started.

### Stopping an endpoint
Endpoints are stopped using the `reactor endpoint-stop` command:

    $ reactor endpoint-stop --domain=<domain> <endpoint name>

For example:

    $ reactor endpoint-stop --domain=example.com www-production
    Please enter admin password for Reactor at api.example.com:
    Contacting Reactor at api.example.com...
    Stopping Reactor endpoint "www-production".
    Waiting for 2 instances to go offline...
    Reactor endpoint "www-production" is now stopped.

### Updating an endpoint
An endpoint's configuration file is updated using the `reactor endpoint-update` command:

    $ reactor endpoint-update --domain=<domain> <endpoint name> <path to config file>

For example:

    $ reactor endpoint-update --domain=example.com www-production www-production.conf
    Please enter admin password for Reactor at api.example.com:
    Contacting Reactor at api.example.com...
    Updating Reactor endpoint "www-production" with configuration file "www-production.conf"...
    Instance min/max are unchanged.
    Template parameters unchanged.
    Instances are still within scale parameters.
    Will not create/destroy any instances.
    Reactor endpoint "www-production" has been updated.

### Removing an endpoint
An endpoint's is removed using the `reactor endpoint-remove` command:

    $ reactor endpoint-remove --domain=<domain> <endpoint name>

For example:

    $ reactor endpoint-remove --domain=example.com www-production
    Please enter admin password for Reactor at api.example.com:
    Contacting Reactor at api.example.com...
    Removing Reactor endpoint "www-production"...
    Endpoint "www-production" is in stopped state.
    Reactor endpoint "www-production" has been removed.

## Instance configuration
Instances are based off of a VMS-enabled virtual machine template.

The instance template must be configured to:
1. Register with Reactor when the instance is ready to accept connections.
1. Provide Reactor with application-specific metrics (optional for applications that use the `http` load-balancing policy.

### Registering with the Reactor system
Regristration with Reactor system is accomplished via the [REST API](api-reference.md#registering_a_new_application_instance):

    #/bin/sh
    curl -X POST http://api.example.com/v1.0/register

### Reporting application-specific metrics
Reporting application-specific metrics is accomplished via the [Reactor API](api-reference.md#reporting_instancespecific_metrics). For example, to report five active connections with a weight of `1` to the `active` metric, the instance would POST the following to Reactor:

    #/bin/sh
    curl -X POST -H 'Content-type: application/json' -d '{ "active" : [1, 5] }' \
        http://api.example.com/v1.0/metrics

For more information on reporting metrics, see the [API Reference](api-reference.md#reporting_instancespecific_metrics).

All applications should, at a minimum, report an `active` metric; otherwise, Reactor will not be able to determine which instances to decommission when scaling the number of instances down.
