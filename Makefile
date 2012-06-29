#!/usr/bin/make -f

VERSION := 1.0

default: dist
.PHONY: default

dist: clean
	@VERSION=$(VERSION) python setup.py bdist --owner root --group root
.PHONY: dist

install: clean
	@VERSION=$(VERSION) python setup.py install
.PHONY: install

clean:
	@rm -rf dist build pancake.egg-info
	@find . -name \*.pyc -exec rm -f {} \;
.PHONY: clean

# Build the development environment by installing all of the dependent packages.
# Check the README for a list of packages that will be installed.
env:
	sudo apt-get -y install nginx
	sudo apt-get -y install python-mako
	sudo apt-get -y install python-zookeeper
	sudo apt-get -y install python-novaclient
	sudo apt-get -y install python-netifaces
	sudo apt-get -y install python-pyramid || sudo easy-install pyramid 
.PHONY: env
