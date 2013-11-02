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
PYTEST_RESULT ?= pytest.xml
PYTEST_FLAGS ?= --junitxml=$(PYTEST_RESULT)
PYLINT_RESULT ?= pylint.txt

all: pylint test dist packages
.PHONY: all

dist:
	@VERSION=$(PACKAGE_VERSION) python$(PYTHON_VER) setup.py sdist
.PHONY: dist

install: dist
	@VERSION=$(PACKAGE_VERSION) python$(PYTHON_VER) setup.py install --prefix=$(DESTDIR)
.PHONY: install

pylint: $(PYLINT_RESULT)
.PHONY: pylint

$(PYLINT_RESULT): $(shell find reactor -name \*.py)
	@pylint --ignore=tests --rcfile=pylintrc reactor | tee $@

test: cache_clean
	@./py.test $(PYTEST_FLAGS) reactor
.PHONY: test

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
	@rm -rf $(DESTDIR)/usr/bin
endif

server_install: dist_clean
ifneq ($(DESTDIR),)
ifneq ($(INIT),)
	@$(INSTALL_DIR) $(DESTDIR)/etc
	@rsync -ruav $(INIT)/ $(DESTDIR)/etc
endif
	@$(INSTALL_DIR) $(DESTDIR)/etc/logrotate.d
	@$(INSTALL_DATA) etc/logrotate.d/reactor $(DESTDIR)/etc/logrotate.d
	@$(INSTALL_DIR) $(DESTDIR)/etc/reactor
	@$(INSTALL_DIR) $(DESTDIR)/etc/reactor/example
	@$(INSTALL_DIR) $(DESTDIR)/etc/reactor/default
	@rsync -ruav example/ $(DESTDIR)/etc/reactor/example
	@rsync -ruav default/ $(DESTDIR)/etc/reactor/default
	@$(INSTALL_DIR) $(DESTDIR)/usr/bin
	@$(INSTALL_BIN) bin/reactor-defaults $(DESTDIR)/usr/bin
	@$(INSTALL_BIN) bin/reactor-server $(DESTDIR)/usr/bin
endif

client_install: dist_clean
ifneq ($(DESTDIR),)
	@$(INSTALL_DIR) $(DESTDIR)/usr/bin
	@$(INSTALL_BIN) bin/reactor $(DESTDIR)/usr/bin
endif

cache_clean:
	@find . -name __pycache__ -exec rm -rf {} \; 2>/dev/null || true
	@find . -name \*.pyc -exec rm -f {} \; 2>/dev/null || true
.PHONY: cache_clean

dist_clean: cache_clean
	@rm -rf dist build reactor.egg-info
	@rm -rf debbuild rpmbuild
.PHONY: dist_clean

clean: dist_clean
	@rm -rf *.deb *.rpm extra/cobalt-novaclient*.*
	@rm -rf pylint.txt pytest.xml
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

python-reactor.deb: $(DEBBUILD)
	@$(INSTALL_DIR) $(DEBBUILD)/python-reactor
	@$(MAKE) dist_install \
	    PYTHON_VER=2.7 \
	    PACKAGES_DIR=dist-packages \
	    DESTDIR=$(CURDIR)/$(DEBBUILD)/python-reactor
	@rsync -ruav packagers/deb/python-reactor/ $(DEBBUILD)/python-reactor
	@sed -i "s/@(VERSION)/$(PACKAGE_VERSION)/" $(DEBBUILD)/python-reactor/DEBIAN/control
	@fakeroot dpkg -b $(DEBBUILD)/python-reactor .
.PHONY: python-reactor.deb

reactor-server.deb: $(DEBBUILD)
	@$(INSTALL_DIR) $(DEBBUILD)/reactor-server
	@$(MAKE) server_install \
	    INIT=etc/upstart \
	    DESTDIR=$(CURDIR)/$(DEBBUILD)/reactor-server
	@rsync -ruav packagers/deb/reactor-server/ $(DEBBUILD)/reactor-server
	@sed -i "s/@(VERSION)/$(PACKAGE_VERSION)/" $(DEBBUILD)/reactor-server/DEBIAN/control
	@fakeroot dpkg -b $(DEBBUILD)/reactor-server .
.PHONY: reactor-server.deb

reactor-client.deb: $(DEBBUILD)
	@$(INSTALL_DIR) $(DEBBUILD)/reactor-client
	@$(MAKE) client_install \
	    DESTDIR=$(CURDIR)/$(DEBBUILD)/reactor-client
	@rsync -ruav packagers/deb/reactor-client/ $(DEBBUILD)/reactor-client
	@sed -i "s/@(VERSION)/$(PACKAGE_VERSION)/" $(DEBBUILD)/reactor-client/DEBIAN/control
	@fakeroot dpkg -b $(DEBBUILD)/reactor-client .
.PHONY: reactor-client.deb

python-reactor.rpm: $(RPMBUILD)
	@rm -rf $(CURDIR)/$(RPMBUILD)/BUILDROOT/*
	@$(MAKE) dist_install \
	    PYTHON_VER=2.6 \
	    PACKAGES_DIR=site-packages \
	    DESTDIR=$(CURDIR)/$(RPMBUILD)/BUILDROOT
	@rpmbuild --with=suggests -bb --buildroot $(CURDIR)/$(RPMBUILD)/BUILDROOT \
	    --define="%_topdir $(CURDIR)/$(RPMBUILD)" \
	    --define="%version $(PACKAGE_VERSION)" \
	    packagers/rpm/python-reactor.spec
	@find $(RPMBUILD) -name \*.rpm -exec mv {} . \;
.PHONY: python-reactor.rpm

reactor-server.rpm: $(RPMBUILD)
	@rm -rf $(CURDIR)/$(RPMBUILD)/BUILDROOT/*
	@$(MAKE) server_install \
	    INIT=etc/sysV \
	    DESTDIR=$(CURDIR)/$(RPMBUILD)/BUILDROOT
	@rpmbuild --with=suggests -bb --buildroot $(CURDIR)/$(RPMBUILD)/BUILDROOT \
	    --define="%_topdir $(CURDIR)/$(RPMBUILD)" \
	    --define="%version $(PACKAGE_VERSION)" \
	    packagers/rpm/reactor-server.spec
	@find $(RPMBUILD) -name \*.rpm -exec mv {} . \;
.PHONY: reactor-server.rpm

reactor-client.rpm: $(RPMBUILD)
	@rm -rf $(CURDIR)/$(RPMBUILD)/BUILDROOT/*
	@$(MAKE) client_install \
	    DESTDIR=$(CURDIR)/$(RPMBUILD)/BUILDROOT
	@rpmbuild --with=suggests -bb --buildroot $(CURDIR)/$(RPMBUILD)/BUILDROOT \
	    --define="%_topdir $(CURDIR)/$(RPMBUILD)" \
	    --define="%version $(PACKAGE_VERSION)" \
	    packagers/rpm/reactor-client.spec
	@find $(RPMBUILD) -name \*.rpm -exec mv {} . \;
.PHONY: reactor-client.rpm

packages: deb-packages rpm-packages
.PHONY: packages

deb-packages: python-reactor.deb reactor-server.deb reactor-client.deb
.PHONY: deb-packages

rpm-packages: python-reactor.rpm reactor-server.rpm reactor-client.rpm
.PHONY: rpm-packages
