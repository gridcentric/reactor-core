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
    version="0.1",
    author="Gridcentric Inc.",
    author_email="support@gridcentric.com",
    url="http://www.gridcentric.com",
    packages=["gridcentric",
              "gridcentric.pancake",
              "gridcentric.pancake.loadbalancer",
              "gridcentric.pancake.zookeeper",
              "gridcentric.pancake.metrics",
              "gridcentric.pancake.cloud"],
    data_files=[
        ("gridcentric/pancake/loadbalancer",
            ["gridcentric/pancake/loadbalancer/nginx.template",
             "gridcentric/pancake/loadbalancer/pancake.conf"])],
    scripts=["bin/pancake"]
)
