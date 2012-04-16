#!/bin/bash

# Ensure the gridcentric nova service does not start.
rm -f etc/init/nova-gridcentric.conf

# Make no sure no nginx sites are enabled.
rm -f etc/nginx/sites-enabled/*
