#!/usr/bin/make -f

all : clean
	python setup.py install --prefix=$$PWD/dist/usr --root=/
	cd $$PWD/dist/usr/lib/python* && [ -d site-packages ] && \
	    mv site-packages dist-packages || true
	mkdir -p $$PWD/dist/etc/init
	install -m0644 etc/pancake.conf $$PWD/dist/etc/init
	cd $$PWD/dist && tar cvzf ../pancake.tgz .
.PHONY: all

clean :
	rm -rf dist build pancake-*
.PHONY: clean

# Build the development environment by installing all of the dependent packages. Check
# README for a list of packages that will be installed.
env :
	sudo apt-get -y install nginx
	sudo apt-get -y install python-mako
	sudo apt-get -y install python-zookeeper
	sudo apt-get -y install python-novaclient
	sudo apt-get -y install python-pyramid || sudo easy-install pyramid 
.PHONY : env
