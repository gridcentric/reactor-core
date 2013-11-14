#!/usr/bin/env python

import os
import re
import subprocess

from setuptools import setup

VERSION = os.getenv("VERSION")

if VERSION is None:
    # Extract the git tag as the version.
    git_describe = subprocess.Popen(
        ["git", "describe", "--tags"],
        stdout=subprocess.PIPE,
        close_fds=True)
    stdout, _ = git_describe.communicate()
    if git_describe.returncode == 0:
        m = re.match(".*-(\d+\.\d+\.\d+)-.*", stdout)
        if m:
            VERSION = m.group(1)

if VERSION is None:
    # Use 0.1, as the version is unknown.
    VERSION = "0.1"

setup(
    name="reactor",
    description="Load balancer and scale manager.",
    version=VERSION,
    author="Gridcentric Inc.",
    author_email="support@gridcentric.com",
    url="http://www.gridcentric.com",
    install_requires=[
        "httplib2",
        "pyramid>=1.2",
        "webob>=1.1",
        "zope.interface>=3.6",
        "Mako>=0.4.2",
        "paste",
        "PasteDeploy>=1.5",
        "zkpython",
        "netifaces",
        "netaddr",
        "python-ldap",
    ],
    test_requires=[
        "mock",
    ],
    packages=[
        "reactor",
        "reactor.loadbalancer",
        "reactor.loadbalancer.dnsmasq",
        "reactor.loadbalancer.nginx",
        "reactor.loadbalancer.haproxy",
        "reactor.loadbalancer.tcp",
        "reactor.loadbalancer.rdp",
        "reactor.cloud",
        "reactor.cloud.osapi",
        "reactor.cloud.osvms",
        "reactor.cloud.docker",
        "reactor.metrics",
        "reactor.objects",
        "reactor.zookeeper",
    ],
    package_data={
        "reactor.loadbalancer.nginx" : [
            "nginx.template",
            "reactor.conf"
        ],
        "reactor.loadbalancer.haproxy" : [
            "haproxy.template"
        ],
        "reactor.loadbalancer.dnsmasq" : [
            "dnsmasq.template"
        ],
        "reactor" : [
            "admin/*.html",
            "admin/include/*.html",
            "admin/include/*.sh",
            "admin/assets/*.js",
            "admin/assets/*.png",
            "admin/assets/*.css",
            "admin/assets/*.sh",
            "admin/assets/lib/*.js",
            "admin/assets/lib/bootstrap/*/*",
        ]
    },
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'reactor = reactor.client:main',
            'reactor-dump = reactor.dump:main',
            'reactor-server = reactor.gui:main',
            'reactor-manager = reactor.manager:main',
        ]
    },
    classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Environment :: Openstack',
          'Intended Audience :: System Administrators',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python',
          'Topic :: Internet :: Proxy Servers',
          'Topic :: System :: Clustering',
    ],
)
