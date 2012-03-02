#!/bin/bash

if [ $# != 2 ]
then
    echo "usage: setup.sh example_server path"
    echo ""
    echo "e.g. setup.sh openstack@openstack-management.gridcentric.ca ''"
    echo "e.g. setup.sh dscannell@dscannll-desktop /home/dscannell/projects/gridcentric/cloud/pancake/example"
    exit 1
fi

EXAMPLE_SERVER=$1
EXAMPLE_PATH=$2

# setup password
passwd

# Acquire the necessary packages
apt-get install nano zip apache2 libapache2-mod-wsgi python-django curl

# Install vms-agent
apt-get install vms-agent
/etc/init.d/vmsagent start

# Get the django application
mkdir -p /web
scp $EXAMPLE_SERVER:$EXAMPLE_PATH/ip_test.zip /web/ip_test.zip
unzip /web/ip_test.zip -d /web
ln -s /web/punchvid/templates /templates

# Get the agent application
scp $EXAMPLE_SERVER:$EXAMPLE_PATH/../clone.d/* /etc/gridcentric/clone.d

# Configure apache
cat /etc/apache2/sites-available/default | sed 's:</VirtualHost>:WSGIScriptAlias / /web/punchvid/django.wsgi\n</VirtualHost>:' - > /etc/apache2/sites-available/punchvid
a2ensite punchvid
a2dissite default
service apache2 reload
