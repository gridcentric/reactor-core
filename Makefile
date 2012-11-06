#!/usr/bin/make -f

VERSION ?= 1.1

RPMBUILD := rpmbuild
DEBBUILD := debbuild

INSTALL_DIR := install -d -m0755 -p

default: dist packages
.PHONY: default

dist: clean
	@VERSION=$(VERSION) python setup.py sdist
.PHONY: dist

install: clean dist
	@VERSION=$(VERSION) python setup.py install
.PHONY: install

clean:
	@rm -rf dist build reactor.egg-info
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

$(RPMBUILD):
	@$(INSTALL_DIR) $(RPMBUILD)
	@$(INSTALL_DIR) $(RPMBUILD)/SRPMS
	@$(INSTALL_DIR) $(RPMBUILD)/BUILD
	@$(INSTALL_DIR) $(RPMBUILD)/BUILDROOT
	@$(INSTALL_DIR) $(RPMBUILD)/SPECS
	@$(INSTALL_DIR) $(RPMBUILD)/RPMS/noarch
	@$(INSTALL_DIR) $(RPMBUILD)/SOURCES
.PHONY: $(RPMBUILD)

$(DEBBUILD):
	@$(INSTALL_DIR) $(DEBBUILD)
.PHONY: $(DEBBUILD)

# Build an agent deb.
deb: $(DEBBUILD)
	@$(INSTALL_DIR) $(DEBBUILD)/reactor-agent
	@rsync -ruav --delete packagers/deb/reactor-agent/ $(DEBBUILD)/reactor-agent
	@rsync -ruav agent/ $(DEBBUILD)/reactor-agent
	@sed -i "s/\(^Version:\).*/\1 $(VERSION)/" $(DEBBUILD)/reactor-agent/DEBIAN/control
	@fakeroot dpkg -b $(DEBBUILD)/reactor-agent .
.PHONY: deb

# Build an agent rpm.
rpm: $(RPMBUILD)
	@rpmbuild -bb --buildroot $(CURDIR)/$(RPMBUILD)/BUILDROOT \
	    --define="%_topdir $(CURDIR)/$(RPMBUILD)" \
	    --define="%version $(VERSION)" \
	    packagers/rpm/reactor-agent.spec
	@find $(RPMBUILD) -name \*.rpm -exec mv {} . \;
.PHONY: rpm

packages: deb rpm
.PHONY: packages
