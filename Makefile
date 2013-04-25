#!/usr/bin/make -f

VERSION ?= 1.1
DESTDIR ?= /usr
ifneq ($(RELEASE),)
PACKAGE_VERSION = $(VERSION).$(RELEASE)
else
PACKAGE_VERSION = $(VERSION).0
endif

RPMBUILD := rpmbuild
DEBBUILD := debbuild

INSTALL_DIR := install -d -m0755 -p
INSTALL_BIN := install -m0755 -p
INSTALL_DATA := install -m0644 -p
PYTHON_VER ?= $(shell python -V 2>&1 | cut -d' ' -f2 | awk -F'.' '{print $$1 "." $$2};')

default: dist packages
.PHONY: default

dist:
	@VERSION=$(PACKAGE_VERSION) python setup.py sdist
.PHONY: dist

install: dist
	@VERSION=$(PACKAGE_VERSION) python setup.py install --prefix=$(DESTDIR)
.PHONY: install

dist_install:
	@VERSION=$(PACKAGE_VERSION) python setup.py bdist -p bdist
	@mkdir -p $(DESTDIR)
	@cd $(DESTDIR) && tar -zxvf $(CURDIR)/dist/reactor-$(PACKAGE_VERSION).bdist.tar.gz
	@mv $(DESTDIR)/usr/local/* $(DESTDIR)/usr; rmdir $(DESTDIR)/usr/local
	@rsync -ruv etc/ $(DESTDIR)/etc

clean:
	@rm -rf dist build reactor.egg-info
	@find . -name \*.pyc -exec rm -f {} \;
	@rm -rf *.deb *.rpm debbuild rpmbuild
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
agent.deb: $(DEBBUILD)
	@$(INSTALL_DIR) $(DEBBUILD)/reactor-agent
	@rsync -ruav --delete packagers/deb/reactor-agent/ $(DEBBUILD)/reactor-agent
	@rsync -ruav agent/ $(DEBBUILD)/reactor-agent
	@sed -i "s/\(^Version:\).*/\1 $(PACKAGE_VERSION)/" $(DEBBUILD)/reactor-agent/DEBIAN/control
	@fakeroot dpkg -b $(DEBBUILD)/reactor-agent .
.PHONY: agent.deb

# Build an agent rpm.
agent.rpm: $(RPMBUILD)
	@rpmbuild --with=suggests -bb --buildroot $(CURDIR)/$(RPMBUILD)/BUILDROOT \
	    --define="%_topdir $(CURDIR)/$(RPMBUILD)" \
	    --define="%version $(PACKAGE_VERSION)" \
	    packagers/rpm/reactor-agent.spec
	@find $(RPMBUILD) -name \*.rpm -exec mv {} . \;
.PHONY: agent.rpm

# Build server packages.
server.deb: $(DEBBUILD)
	@$(INSTALL_DIR) $(DEBBUILD)/reactor-server
	@rsync -ruav --delete packagers/deb/reactor-server/ $(DEBBUILD)/reactor-server
	@$(MAKE) dist_install DESTDIR=$(DEBBUILD)/reactor-server
	@$(INSTALL_BIN) bin/reactor-setup $(DEBBUILD)/reactor-server/usr/bin
	@sed -i "s/\(^Version:\).*/\1 $(PACKAGE_VERSION)/" $(DEBBUILD)/reactor-server/DEBIAN/control
	@fakeroot dpkg -b $(DEBBUILD)/reactor-server .
.PHONY: server.deb

server.rpm: $(RPMBUILD)
	@rm -rf $(CURDIR)/$(RPMBUILD)/BUILDROOT/*
	@$(MAKE) dist_install DESTDIR=$(CURDIR)/$(RPMBUILD)/BUILDROOT
	@rpmbuild --with=suggests -bb --buildroot $(CURDIR)/$(RPMBUILD)/BUILDROOT \
	    --define="%_topdir $(CURDIR)/$(RPMBUILD)" \
	    --define="%version $(PACKAGE_VERSION)" \
	    packagers/rpm/reactor-server.spec
	@find $(RPMBUILD) -name \*.rpm -exec mv {} . \;
.PHONY: server.rpm

packages: agent.deb agent.rpm server.deb server.rpm
.PHONY: packages
