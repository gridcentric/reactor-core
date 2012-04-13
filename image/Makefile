#!/usr/bin/make -f

default:
	@echo "Use the target build-X for some hypervisor X (e.g. xen, kvm)."
.PHONY: default

clean:
	@rm -f local/*
.PHONY: clean

# NOTE: The python zookeeper bindings are installed separately
# via a generated contrib package. This is due to several problems
# in the older packaged version, hence we build from source and
# install the tarball mechanism.

build-%:
	@rm -rf dist-$*
	PATH=$$PWD:$$PATH ubuntu-vm-builder $* oneiric \
	    --tmpfs=- \
	    --destdir=$$PWD/dist \
	    --rootsize=4096 \
	    --swapsize=1024 \
	    --hostname=pancake \
	    --execscript=deploy \
	    --domain=gridcentric.com \
	    --user=pancake \
	    --name=Pancake \
	    --pass=p4nc4k3gr1d \
	    --addpkg=ssh \
	    --addpkg=zookeeper \
	    --addpkg=zookeeperd \
	    --addpkg=nginx \
	    --addpkg=python-mako \
	    --addpkg=python-novaclient \
	    --addpkg=python-pyramid
