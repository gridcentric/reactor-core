# Build the development environment by installing all of the dependent packages. Check
# README for a list of packages that will be installed.
env : zookeeper-3.4.3
	sudo apt-get -y install nginx
	sudo apt-get -y install python-mako
	sudo apt-get -y install python-zookeeper
	sudo apt-get -y install python-novaclient
	sudo apt-get -y install python-pyramid || sudo easy-install pyramid 
.PHONY : env

# Install the latest package
zookeeper-3.4.3 : zookeeper-3.4.3.tar.gz
	sudo apt-get install -y autoconf libtool libcppunit-1.12-1 libcppunit-dev ant python-dev
	tar xzf zookeeper-3.4.3.tar.gz
	cd zookeeper-3.4.3/src/c; autoreconf -if && ./configure && sudo make install
	cd zookeeper-3.4.3/src/contrib/zkpython; sudo ant install

# Grap the zookeeper-3.4.* package	
zookeeper-3.4.3.tar.gz : 
	wget http://apache.parentingamerica.com//zookeeper/zookeeper-3.4.3/zookeeper-3.4.3.tar.gz
