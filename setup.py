#!/usr/bin/env python

import os

from setuptools import setup

setup(
    name="reactor",
    description="Load balancer and scale manager.",
    version=os.getenv("VERSION") or "0.1",
    author="Gridcentric Inc.",
    author_email="support@gridcentric.com",
    url="http://www.gridcentric.com",
    install_requires=[
        "httplib2",
        "pyramid>=1.2",
        "webob>=1.1",
        "zope.interface>=3.6",
        "Mako>=0.4.2",
        "PasteDeploy>=1.5",
        "zookeeper",
        "netifaces",
        "netaddr",
        "python-ldap",
        "markdown",
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
            "admin/docs/*.md",
            "admin/docs/*.html",
            "admin/docs/clouds/*.md",
            "admin/docs/loadbalancers/*.md",
        ]
    },
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'reactor = reactor.client:main',
            'reactor-server = reactor.server:main',
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
