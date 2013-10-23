<h1>Installation</h1>

[TOC]

# Via setup.sh

You can install reactor automatically via a [setup script](/assets/setup.sh).

    curl https://raw.github.com/gridcentric/reactor-core/master/setup.sh | sudo bash -

# Via cloud-init

Reactor installed via a cloud-init, using the [setup script](/assets/setup.sh).

Simply download this file, and pass it as the user-data to a new instance.

    nova boot --user-data setup.sh reactor-instance

# From Packages

Reactor is normally installed from cloud-init, but you may choose to install it
manually in your system directly from packages. Keep in mind that in such case
you will need to configure bindings with your load balancer.

The following two sections synthesize the download instructions found elsewhere
for the two main distros.

## Ubuntu

First get our public key.

    wget -O - http://downloads.gridcentric.com/packages/gridcentric.key | sudo apt-key add -

Second, configure a new APT repo.

    echo deb http://downloads.gridcentric.com/packages/reactor/reactor-core/ubuntu/ gridcentric multiverse | sudo tee /etc/apt/sources.list.d/reactor.list

Now let apt do its job.

    sudo apt-get update
    sudo apt-get install -y reactor-server

## Centos 6.x

In this case, you need to enable the EPEL repository to pull in additioinal dependencies.

    rpm --import http://dl.fedoraproject.org/pub/epel/RPM-GPG-KEY-EPEL-6
    rpm -Uvh http://fedora.mirror.nexicom.net/epel/6/i386/epel-release-6-8.noarch.rpm

Also import our public key.

    rpm --import http://downloads.gridcentric.com/packages/gridcentric.key

Now create a yum repo for reactor, in e.g. `/etc/yum.repos.d/reactor.repo`.

    [reactor]
    name=reactor
    baseurl=http://downloads.gridcentric.com/packages/reactor/reactor-core/centos
    enabled=1
    gpgcheck=1

Now unleash yum. Several dependencies will be pulled in, including the JRE for Zookeeper's benefit.

    yum install -y nginx haproxy dnsmasq zookeeper socat
    yum install -y reactor-server

# From Source

You can install the Reactor packages directly from source.

You can either use `pip` to install the packages.

    sudo pip install https://raw.github.com/gridcentric/reactor-core/master/setup.py

Or, you can clone the repo and run `setup.py`.

    git clone https://github.com/gridcentric/reactor-core
    cd reactor-core && sudo python setup.py install
