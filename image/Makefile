#!/usr/bin/make -f

default:
	@echo "Use the target build-X for some hypervisor X (e.g. xen, kvm)."
.PHONY: default

clean:
	@rm -f local/*
.PHONY: clean

build-%:
	@mkdir -p dist
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
	    --addpkg=python-zookeeper \
	    --addpkg=nginx \
	    --addpkg=python-mako \
	    --addpkg=python-novaclient \
	    --addpkg=python-pyramid
