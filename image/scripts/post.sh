#!/bin/bash

# Ensure the gridcentric nova service does not start.
rm -f etc/init/nova-gridcentric.conf

# Make no sure no nginx sites are enabled.
rm -f etc/nginx/sites-enabled/*

# Enable log rotation.
cat >/etc/logrotate.d/pancake <<EOF
/var/log/pancake.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 0640 root root
    sharedscripts
}
EOF
