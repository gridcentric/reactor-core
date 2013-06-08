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
    install_requires=[
        "httplib2",
        "pyramid>=1.2",
        "webob>=1.1",
        "zope.interface>=3.6",
        "Mako>=0.4.2",
        "PasteDeploy>=1.5",
        "zookeeper",
        "netifaces",
        "python-ldap",
    ],
    packages=find_packages(),
    package_data={
        "reactor.loadbalancer.nginx" : ["nginx.template", "reactor.conf"],
        "reactor.loadbalancer.dnsmasq" : ["dnsmasq.template"],
        "reactor.demo" : ["reactor.png"],
        "reactor.server" : ["admin/*.html",
                            "admin/include/*.html",
                            "admin/assets/*.js",
                            "admin/assets/*.png",
                            "admin/assets/*.css",
                            "admin/assets/lib/*.js",
                            "admin/assets/lib/bootstrap/*/*"]
    },
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'reactor = reactor.cli:main',
            'reactor-server = reactor.cli:server',
            'reactor-demo = reactor.demo:main'
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
