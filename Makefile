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
PACKAGES_DIR ?= dist-packages

default: dist packages
.PHONY: default

dist:
	@VERSION=$(PACKAGE_VERSION) python$(PYTHON_VER) setup.py sdist
.PHONY: dist

install: dist
	@VERSION=$(PACKAGE_VERSION) python$(PYTHON_VER) setup.py install --prefix=$(DESTDIR)
.PHONY: install

dist_install: dist_clean
	@VERSION=$(PACKAGE_VERSION) python$(PYTHON_VER) setup.py bdist -p bdist
ifneq ($(DESTDIR),)
	@$(INSTALL_DIR) $(DESTDIR)
	@cd $(DESTDIR) && tar -zxf $(CURDIR)/dist/reactor-$(PACKAGE_VERSION).bdist.tar.gz
	@mv $(DESTDIR)/usr/local/* $(DESTDIR)/usr; rmdir $(DESTDIR)/usr/local
	@[ -d $(DESTDIR)/usr/lib*/python$(PYTHON_VER) ] || \
	    (cd $(DESTDIR)/usr/lib* && mv python* python$(PYTHON_VER))
	@[ -d $(DESTDIR)/usr/lib*/python$(PYTHON_VER)/$(PACKAGES_DIR) ] || \
	    (cd $(DESTDIR)/usr/lib*/python$(PYTHON_VER) && mv *-packages $(PACKAGES_DIR))
ifneq ($(INIT),)
	@$(INSTALL_DIR) $(DESTDIR)/etc
	@rsync -ruav $(INIT)/ $(DESTDIR)/etc
endif
	@$(INSTALL_DIR) $(DESTDIR)/etc/logrotate.d
	@$(INSTALL_DATA) etc/logrotate.d/reactor $(DESTDIR)/etc/logrotate.d
endif

dist_clean:
	@rm -rf dist build reactor.egg-info
	@rm -rf debbuild rpmbuild
	@find . -name \*.pyc -exec rm -f {} \;
.PHONY: dist_clean

clean: dist_clean
	@rm -rf *.deb *.rpm
.PHONY: clean

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

# Build agent packages.
agent.deb: $(DEBBUILD)
	@$(INSTALL_DIR) $(DEBBUILD)/reactor-agent
	@rsync -ruav --delete packagers/deb/reactor-agent/ $(DEBBUILD)/reactor-agent
	@rsync -ruav agent/ $(DEBBUILD)/reactor-agent
	@sed -i "s/\(^Version:\).*/\1 $(PACKAGE_VERSION)/" $(DEBBUILD)/reactor-agent/DEBIAN/control
	@fakeroot dpkg -b $(DEBBUILD)/reactor-agent .
.PHONY: agent.deb

agent.rpm: $(RPMBUILD)
	@rpmbuild --with=suggests -bb \
	    --buildroot $(CURDIR)/$(RPMBUILD)/BUILDROOT \
	    --define="%_topdir $(CURDIR)/$(RPMBUILD)" \
	    --define="%version $(PACKAGE_VERSION)" \
	    packagers/rpm/reactor-agent.spec
	@find $(RPMBUILD) -name \*.rpm -exec mv {} . \;
.PHONY: agent.rpm

# Build server packages.
server.deb: $(DEBBUILD)
	@$(INSTALL_DIR) $(DEBBUILD)/reactor-server
	@$(MAKE) dist_install \
	    PYTHON_VER=2.7 \
	    PACKAGES_DIR=dist-packages \
	    INIT=etc/upstart \
	    DESTDIR=$(DEBBUILD)/reactor-server
	@rsync -ruav packagers/deb/reactor-server/ $(DEBBUILD)/reactor-server
	@sed -i "s/\(^Version:\).*/\1 $(PACKAGE_VERSION)/" $(DEBBUILD)/reactor-server/DEBIAN/control
	@fakeroot dpkg -b $(DEBBUILD)/reactor-server .
.PHONY: server.deb

server.rpm: $(RPMBUILD)
	@rm -rf $(CURDIR)/$(RPMBUILD)/BUILDROOT/*
	@$(MAKE) dist_install \
	    PYTHON_VER=2.6 \
	    PACKAGES_DIR=site-packages \
	    INIT=etc/sysV \
	    DESTDIR=$(CURDIR)/$(RPMBUILD)/BUILDROOT
	@rpmbuild --with=suggests -bb --buildroot $(CURDIR)/$(RPMBUILD)/BUILDROOT \
	    --define="%_topdir $(CURDIR)/$(RPMBUILD)" \
	    --define="%version $(PACKAGE_VERSION)" \
	    packagers/rpm/reactor-server.spec
	@find $(RPMBUILD) -name \*.rpm -exec mv {} . \;
.PHONY: server.rpm

packages: agent.deb agent.rpm server.deb server.rpm
.PHONY: packages
