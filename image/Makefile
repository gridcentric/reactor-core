#!/usr/bin/make -f

FLAVOR     := oneiric
ROOTSIZE   := 4096
SWAPSIZE   := 1024
HOSTNAME   := pancake
DOMAINNAME := gridcentric.com
USERNAME   := pancake
PASSWORD   := p4nc4k3gr1d

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

PACKAGE_CMDLINE := $(PACKAGES:%=--addpkg=%)

ARGS := --rootsize=$(ROOTSIZE) \
	--swapsize=$(SWAPSIZE) \
	--hostname=$(HOSTNAME) \
	--execscript=deploy \
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

chroot-%:
	@# NOTE: The hypervisor doesn't matter here. 
	PATH=$$PWD:$$PATH ubuntu-vm-builder kvm $* \
	    --destdir=$$PWD/dist-$* \
	    --only-chroot \
	    --chroot-dir=$@ \
	    $(ARGS)

build-%: chroot-$(FLAVOR)
	@rm -rf dist-$*
	PATH=$$PWD:$$PATH ubuntu-vm-builder $* $(FLAVOR) \
	    --destdir=$$PWD/dist-$* \
	    --existing-chroot=chroot-$(FLAVOR) \
	    $(ARGS)
