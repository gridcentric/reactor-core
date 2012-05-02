#!/bin/bash

if [ $# != 2 ]
then
    echo "usage: setup.sh <pancake-project-path (for scp)> <pancake-server>"
    echo ""
    echo "e.g. setup.sh dscannell@dscannell-desktop:/home/dscannell/projects/gridcentric/pancake dscannell-desktop"
    exit 1
fi

PANCAKE_PATH=$1
PANCAKE_SERVER=$2

# Acquire the necessary packages.
apt-get install -y nano zip apache2 libapache2-mod-wsgi python-django curl

# Install vms-agent.
apt-get install vms-agent
/etc/init.d/vmsagent start

# Install the pancake agent script.
scp $PANCAKE_PATH/clone.d/90_pancake /etc/gridcentric/clone.d
sed -i -e "s:host=\"pancake\":host=\"$PANCAKE_SERVER\":" /etc/gridcentric/clone.d/90_pancake
chmod +x /etc/gridcentric/clone.d/90_pancake

# Get the django application.
mkdir -p /web
scp $PANCAKE_PATH/example/ip_test.zip /web/ip_test.zip
unzip /web/ip_test.zip -d /web
ln -s /web/punchvid/templates /templates

# Configure apache.
cat /etc/apache2/sites-available/default | \
    sed -e 's:</VirtualHost>:WSGIScriptAlias / /web/punchvid/django.wsgi\n</VirtualHost>:' > \
    /etc/apache2/sites-available/punchvid
a2ensite punchvid
a2dissite default
service apache2 reload
