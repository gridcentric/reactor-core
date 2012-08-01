#!/usr/bin/env python

import os

try:
        from setuptools import setup, find_packages
except ImportError:
        from ez_setup import use_setuptools
        use_setuptools()
        from setuptools import setup, find_packages

setup(
    name="pancake",
    description="Gridcentric load balancer and scale manager (pancake).",
    version=os.getenv("VERSION"),
    author="Gridcentric Inc.",
    author_email="support@gridcentric.com",
    url="http://www.gridcentric.com",
    packages=["gridcentric",
              "gridcentric.pancake",
              "gridcentric.pancake.loadbalancer",
              "gridcentric.pancake.zookeeper",
              "gridcentric.pancake.metrics",
              "gridcentric.pancake.cloud",
              "gridcentric.pancake.cloud.nova",
              "gridcentric.pancake.cloud.nova.client"],
    package_data={'gridcentric.pancake.loadbalancer':\
            ["nginx.template", "dnsmasq.template", "pancake.conf"]},
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'pancake = gridcentric.pancake.cli:main'
        ]
    }
)
