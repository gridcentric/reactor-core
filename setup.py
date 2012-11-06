#!/usr/bin/env python

import os

try:
        from setuptools import setup, find_packages
except ImportError:
        from ez_setup import use_setuptools
        use_setuptools()
        from setuptools import setup, find_packages

def all_files(path):
    found = {}
    for root, dirs, files in os.walk(path):
        package = root.replace('/', '.')
        found[package] = files
    return found

# Index all the administration console files.
admin_files = all_files('reactor/admin')

setup(
    name="reactor",
    description="Load balancer and scale manager.",
    version=os.getenv("VERSION"),
    author="Gridcentric Inc.",
    author_email="support@gridcentric.com",
    url="http://www.gridcentric.com",
    packages=["reactor",
              "reactor.appliance",
              "reactor.loadbalancer",
              "reactor.zookeeper",
              "reactor.metrics",
              "reactor.cloud"
    ] + admin_files.keys(),
    package_data={'reactor.loadbalancer':\
            ["nginx.template", "dnsmasq.template", "reactor.conf"]},
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'reactor-demo = reactor.demo:main',
            'reactor = reactor.cli:main',
            'reactor-server = reactor.cli:server'
        ]
    }
)
