Name: reactor-manager
Summary: Reactor manager
Version: %{version}
Release: 1
Group: System
License: Copyright 2012 GridCentric Inc.
URL: http://www.gridcentric.com
Packager: GridCentric Inc. <support@gridcentric.com>
Requires: reactor-client
Requires: python-reactor = %{version}
Requires: python-netifaces, python-netaddr
Requires: python-zookeeper
# Unfortunately, we don't really have any way of
# specifying soft dependencies. For now, we rely
# on the cloud-init file to install some of these,
# and we just leave them out of the required spec.
# Recommends: python-novaclient, cobalt-novaclient
# Recommends: socat, zookeeper, nginx, haproxy
# Recommends: dnsmasq
BuildRoot: %{_tmppath}/%{name}.%{version}-buildroot
AutoReq: no
AutoProv: no

# see Trac ticket #449
%global _binary_filedigest_algorithm 1
# Don't strip the binaries.
%define __os_install_post %{nil}

%description
Reactor manager.

%install
true

%files
/usr/bin/reactor-manager
/etc/init.d/reactor-manager
/etc/reactor/manager.conf
/etc/logrotate.d/reactor-manager

%post
if [ "$1" = "1" ]; then
    chkconfig reactor-manager on
    service reactor-manager start
else
    service reactor-manager restart
fi

%preun
if [ "$1" = "0" ]; then
    service reactor-manager stop
    chkconfig reactor-manager off
fi

%changelog
* Tue Nov 12 2012 Adin Scannell <adin@scannell.ca>
- Create package
