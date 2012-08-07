#!/usr/bin/make -f

FLAVOR     := oneiric
ROOTSIZE   := 4096
SWAPSIZE   := 1024
HOSTNAME   := reactor
DOMAINNAME := gridcentric.com
USERNAME   := reactor
PASSWORD   := p4nc4k3gr1d
VERSION    ?= unknown

# NOTE: The python zookeeper bindings are installed separately
# via a generated contrib package. This is due to several problems
# in the older packaged version, hence we build from source and
# install the tarball mechanism. See the root Makefile for where
# this is done.

PACKAGES :=
PACKAGES += ssh
PACKAGES += zookeeper
PACKAGES += zookeeperd
PACKAGES += nginx
PACKAGES += python-mako
PACKAGES += python-novaclient
PACKAGES += python-pyramid
PACKAGES += python-netifaces
PACKAGES += dnsmasq
PACKAGES += graphviz
PACKAGES += curl
PACKAGES += iptables

PACKAGE_CMDLINE := $(PACKAGES:%=--addpkg=%)

ARGS := --rootsize=$(ROOTSIZE) \
	--swapsize=$(SWAPSIZE) \
	--hostname=$(HOSTNAME) \
	--execscript=deploy \
	--firstboot=$(CURDIR)/boot \
	--domain=$(DOMAINNAME) \
	--user=$(USERNAME) \
	--name=$(USERNAME) \
	--pass=$(PASSWORD) \
	$(PACKAGE_CMDLINE)

default:
	@echo "Use the target build-X for some hypervisor X (e.g. xen, kvm)."
.PHONY: default

clean:
	@rm -f local/*
.PHONY: clean

chroot-%: Makefile
	@rm -rf $@
	PATH=$(CURDIR):$$PATH ubuntu-vm-builder kvm $* \
	    --destdir=$(CURDIR)/dist-$* \
	    --only-chroot \
	    --chroot-dir=$@ \
	    $(ARGS)

build-%: chroot-$(FLAVOR)
	@rm -rf dist-$*
	PATH=$(CURDIR):$$PATH ubuntu-vm-builder $* $(FLAVOR) \
	    --destdir=$(CURDIR)/dist-$* \
	    --existing-chroot=chroot-$(FLAVOR) \
	    $(ARGS)
	@mv dist-$*/*.qcow2 dist-$*/reactor-$(VERSION).qcow2
