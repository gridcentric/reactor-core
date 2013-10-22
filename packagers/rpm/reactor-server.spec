Name: reactor-server
Summary: Reactor server
Version: %{version}
Release: 1
Group: System
License: Copyright 2012 GridCentric Inc.
URL: http://www.gridcentric.com
Packager: GridCentric Inc. <support@gridcentric.com>
Requires: python-reactor
Requires: iptables, curl, openssh-clients
Requires: python-paste, python-pyramid, python-mako
Requires: python-netifaces, python-ldap
Requires: python-netaddr, python-webob
Requires: python-zookeeper
# Unfortunately, we don't really have any way of
# specifying soft dependencies. For now, we rely
# on the cloud-init file to install some of these,
# and we just leave them out of the required spec.
# Recommends: python-novaclient, cobalt-novaclient
# Recommends: socat, zookeeper, nginx, haproxy
BuildRoot: %{_tmppath}/%{name}.%{version}-buildroot
AutoReq: no
AutoProv: no

# see Trac ticket #449
%global _binary_filedigest_algorithm 1
# Don't strip the binaries.
%define __os_install_post %{nil}

%description
Reactor server.

%install
true

%files
/usr/bin/reactor-setup
/usr/bin/reactor-defaults
/etc/init.d/reactor
/etc/logrotate.d/reactor
/etc/reactor/

%post
if [ "$1" = "1" ]; then
    chkconfig reactor on
    service reactor start
else
    service reactor restart
fi

%preun
if [ "$1" = "0" ]; then
    service reactor stop
    chkconfig reactor off
fi

%changelog
* Tue Apr 23 2012 Adin Scannell <adin@scannell.ca>
- Create package
