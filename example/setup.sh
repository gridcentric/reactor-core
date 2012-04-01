#!/bin/bash

if [ $# != 3 ]
then
    echo "usage: setup.sh server_user example_server pancake_project_path"
    echo ""
    echo "e.g. setup.sh dscannell dscannell-desktop /home/dscannell/projects/gridcentric/pancake"
    exit 1
fi

EXAMPLE_USER=$1
EXAMPLE_SERVER=$2
EXAMPLE_PATH=$3

EXAMPLE_BASE=$EXAMPLE_USER@$EXAMPLE_SERVER:$EXAMPLE_PATH

# Acquire the necessary packages
apt-get install -y nano zip apache2 libapache2-mod-wsgi python-django curl

# Install vms-agent
apt-get install vms-agent
/etc/init.d/vmsagent start

# Install the pancake agent script
scp $EXAMPLE_BASE/clone.d/* ./
cat ./90_pancake | sed "s:PANCAKE_HOST:$EXAMPLE_SERVER:" - > /etc/gridcentric/clone.d/90_pancake
chmod +x /etc/gridcentric/clone.d/90_pancake


# Get the django application
mkdir -p /web
scp $EXAMPLE_BASE/example/ip_test.zip /web/ip_test.zip
unzip /web/ip_test.zip -d /web
ln -s /web/punchvid/templates /templates


# Configure apache
cat /etc/apache2/sites-available/default | sed 's:</VirtualHost>:WSGIScriptAlias / /web/punchvid/django.wsgi\n</VirtualHost>:' - > /etc/apache2/sites-available/punchvid
a2ensite punchvid
a2dissite default
service apache2 reload
