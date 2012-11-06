#!/usr/bin/env python

import os

try:
        from setuptools import setup, find_packages
except ImportError:
        from ez_setup import use_setuptools
        use_setuptools()
        from setuptools import setup, find_packages

setup(
    name="reactor",
    description="Load balancer and scale manager.",
    version=os.getenv("VERSION"),
    author="Gridcentric Inc.",
    author_email="support@gridcentric.com",
    url="http://www.gridcentric.com",
    packages=["reactor",
              "reactor.loadbalancer",
              "reactor.zookeeper",
              "reactor.metrics",
              "reactor.cloud"],
    package_data={'reactor.loadbalancer':\
            ["nginx.template", "dnsmasq.template", "reactor.conf"]},
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'reactor = reactor.cli:main'
        ]
    }
)
