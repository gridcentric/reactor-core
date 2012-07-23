#!/usr/bin/make -f

VERSION := $(shell date "+%Y%m%d.%H%M%S")
PANCAKE_PATH :=

RPMBUILD := rpmbuild
DEBBUILD := debbuild

INSTALL_DIR := install -d -m0755 -p

default:
	@echo "Nothing to be done."
.PHONY: default

prep:
ifeq ($(PANCAKE_PATH),)
	@echo "You must define PANCAKE_PATH to call prep." && false
else
	@mkdir -p image/local
	@cp -a $(PANCAKE_PATH)/dist/* image/local
endif
.PHONY: prep

# Install the latest package (for python bindings).
contrib/zookeeper-3.4.3: contrib/zookeeper-3.4.3.tar.gz Makefile
	@cd contrib && tar xzf zookeeper-3.4.3.tar.gz
	@cd contrib/zookeeper-3.4.3/src/c && autoreconf -if && ./configure

# Build the appropriate python bindings.
image/contrib/python-zookeeper-3.4.3.tgz: contrib/zookeeper-3.4.3 Makefile
	@mkdir -p dist-zookeeper
	@mkdir -p image/contrib
	@cd contrib/zookeeper-3.4.3/src/c && make install DESTDIR=$$PWD/../../../../dist-zookeeper/
	@cd contrib/zookeeper-3.4.3/src/contrib/zkpython && ant tar-bin
	@cd dist-zookeeper && tar zxf ../contrib/zookeeper-3.4.3/build/contrib/zkpython/dist/*.tar.gz
	@cd dist-zookeeper && mv usr/local/* usr && rm -rf usr/local
	@cd dist-zookeeper && fakeroot tar zcvf ../$@ .
	@rm -rf dist-zookeeper

# Install the last stable nginx.
contrib/nginx-1.2.1: contrib/nginx-1.2.1.tar.gz Makefile
	@cd contrib && tar xzf nginx-1.2.1.tar.gz
	@cd contrib && tar xzf nginx-sticky-module-1.0.tar.gz
	@cd contrib/nginx-1.2.1 && ./configure \
	    --add-module=../nginx-sticky-module-1.0/ \
	    --with-http_ssl_module \
	    --prefix=/usr \
	    --conf-path=/etc/nginx/nginx.conf \
	    --pid-path=/var/run/nginx.pid \
	    --lock-path=/var/lock/nginx.lck \
	    --error-log-path=/var/log/nginx/error.log \
	    --http-log-path=/var/log/nginx/access.log

# Build the appropriate nginx packages.
image/contrib/nginx-1.2.1.tgz: contrib/nginx-1.2.1 Makefile
	@mkdir -p dist-nginx
	@mkdir -p image/contrib
	@cd contrib/nginx-1.2.1 && $(MAKE) install DESTDIR=$$PWD/../../dist-nginx/
	@rm -rf dist-nginx/usr/html
	@rm -rf dist-nginx/etc/
	@mkdir -p dist-nginx/usr/local/nginx/client_body_temp
	@cd dist-nginx && fakeroot tar zcvf ../$@ .
	@rm -rf dist-nginx

# Build the local overlays.
image/local: Makefile
	@mkdir -p image/local
image/local/local.tgz: $(shell find local -type f -o -type d) Makefile
	@rm -rf image/local/local.tgz
	@cd local && fakeroot tar cvzf ../image/local/local.tgz .

# Build a virtual machine image for the given hypervisor.
image-%: image/local/local.tgz \
	 image/contrib/python-zookeeper-3.4.3.tgz \
	 image/contrib/nginx-1.2.1.tgz
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

contrib/cx_Freeze-4.2.3: contrib/cx_Freeze-4.2.3.tar.gz Makefile
	@cd contrib && tar xzf cx_Freeze-4.2.3.tar.gz
	@cd contrib/cx_Freeze-4.2.3 && python setup.py build

demo: contrib/cx_Freeze-4.2.3
ifeq ($(PANCAKE_PATH),)
	@echo "You must define PANCAKE_PATH to call demo." && false
else
	@make -C demo
	@mkdir -p tmp-cxfreeze
	@cd contrib/cx_Freeze-4.2.3 && python setup.py install --root=$(CURDIR)/tmp-cxfreeze
	LD_LIBRARY_PATH=tmp-cxfreeze/usr/local/lib/ \
	 PYTHONPATH=$(PANCAKE_PATH):`ls -1d tmp-cxfreeze/usr/local/lib/python*/dist-packages/` \
	 tmp-cxfreeze/usr/local/bin/cxfreeze demo/reactor-viz \
	 --target-dir reactor-demo-$(VERSION)
	@rm -rf tmp-cxfreeze
	@fakeroot tar czvf reactor-demo-$(VERSION).tgz reactor-demo-$(VERSION)
	@rm -rf reactor-demo reactor-demo-$(VERSION)
endif
.PHONY: demo

clean:
	@sudo make -C image clean
	@make -C demo clean
	@rm -rf $(RPMBUILD) $(DEBBUILD) *.rpm *.deb
	@rm -rf tmp-* reactor-demo-*
.PHONY: clean
