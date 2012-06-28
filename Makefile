#!/usr/bin/make -f

VERSION := $(shell date "+%Y%m%d.%H%M%S")

RPMBUILD := rpmbuild
DEBBUILD := debbuild

INSTALL_DIR := install -d -m0755 -p

all: clean
	@VERSION=$(VERSION) python setup.py install --prefix=$(CURDIR)/dist/usr --root=/
	@cd $(CURDIR)/dist/usr/lib/python* && [ -d site-packages ] && \
	    mv site-packages dist-packages || true
	@mkdir -p $(CURDIR)/dist/etc/init
	@install -m0644 etc/pancake.conf $(CURDIR)/dist/etc/init
	@cd $(CURDIR)/dist && tar cvzf ../pancake-$(VERSION).tgz .
.PHONY: all

clean:
	@make -C image clean
	@rm -rf dist build pancake.* pancake-*.tgz
	@rm -rf $(RPMBUILD) $(DEBBUILD) *.rpm *.deb
.PHONY: clean

# Install the latest package (for python bindings).
contrib/zookeeper-3.4.3: contrib/zookeeper-3.4.3.tar.gz
	@cd contrib; tar xzf zookeeper-3.4.3.tar.gz
	@cd contrib/zookeeper-3.4.3/src/c; autoreconf -if && ./configure

# Build the appropriate python bindings.
image/contrib/python-zookeeper-3.4.3.tgz: contrib/zookeeper-3.4.3
	@mkdir -p dist-zookeeper
	@cd contrib/zookeeper-3.4.3/src/c; make install DESTDIR=$$PWD/../../../../dist-zookeeper/
	@cd contrib/zookeeper-3.4.3/src/contrib/zkpython; ant tar-bin
	@cd dist-zookeeper; tar zxf ../contrib/zookeeper-3.4.3/build/contrib/zkpython/dist/*.tar.gz
	@cd dist-zookeeper; mv usr/local/* usr; rm -rf usr/local
	@cd dist-zookeeper; fakeroot tar zcvf ../$@ .
	@rm -rf dist-zookeeper

# Install the last stable nginx.
contrib/nginx-1.2.1: contrib/nginx-1.2.1.tar.gz
	@cd contrib; tar xzf nginx-1.2.1.tar.gz
	@cd contrib; tar xzf nginx-sticky-module-1.0.tar.gz
	@cd contrib/nginx-1.2.1; ./configure \
	    --add-module=../nginx-sticky-module-1.0/ \
	    --prefix=/usr \
	    --conf-path=/etc/nginx/nginx.conf \
	    --pid-path=/var/run/nginx.pid \
	    --lock-path=/var/lock/nginx.lck \
	    --error-log-path=/var/log/nginx/error.log \
	    --http-log-path=/var/log/nginx/access.log

# Build the appropriate nginx packages.
image/contrib/nginx-1.2.1.tgz:
	@mkdir -p dist-nginx
	@cd contrib/nginx-1.2.1; $(MAKE) install DESTDIR=$$PWD/../../dist-nginx/
	@cd dist-nginx; fakeroot tar zcvf ../$@ .
	#@rm -rf dist-nginx

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

# Build a virtual machine image for the given hypervisor.
image-%: all image/contrib/python-zookeeper-3.4.3.tgz
	@mkdir -p image/local
	@cp pancake-$(VERSION).tgz image/local
	@sudo make -C image build-$*

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
	@$(INSTALL_DIR) $(DEBBUILD)/pancake-agent
	@rsync -ruav --delete packagers/deb/pancake-agent/ $(DEBBUILD)/pancake-agent
	@rsync -ruav agent/ $(DEBBUILD)/pancake-agent
	@sed -i "s/\(^Version:\).*/\1 $(VERSION)/" $(DEBBUILD)/pancake-agent/DEBIAN/control
	@fakeroot dpkg -b $(DEBBUILD)/pancake-agent .
.PHONY: deb

# Build an agent rpm.
rpm: $(RPMBUILD)
	@rpmbuild -bb --buildroot $(CURDIR)/$(RPMBUILD)/BUILDROOT \
	    --define="%_topdir $(CURDIR)/$(RPMBUILD)" \
	    --define="%version $(VERSION)" \
	    packagers/rpm/pancake-agent.spec
	@find $(RPMBUILD) -name \*.rpm -exec mv {} . \;
.PHONY: rpm

packages: deb rpm
.PHONY: packages
