# Build the development environment by installing all of the dependent packages. Check
# README for a list of packages that will be installed.
env : zookeeper-3.4.3
	sudo apt-get -y install nginx python-mako
	sudo apt-get -y install python-pyramid || sudo easy-install pyramid 
.PHONY : env

# Install the latest package
zookeeper-3.4.3 : zookeeper-3.4.3.tar.gz
	tar xzf zookeeper-3.4.3.tar.gz
	cd zookeeper-3.4.3/src/c; autoreconf -if && ./configure && sudo make install
	cd zookeeper-3.4.3/src/contrib/zkpython; sudo ant install

# Grap the zookeeper-3.4.* package	
zookeeper-3.4.3.tag.gz : 
	wget http://apache.parentingamerica.com//zookeeper/zookeeper-3.4.3/zookeeper-3.4.3.tar.gz
