Name: reactor-server
Summary: Reactor server
Version: %{version}
Release: 1
Group: System
License: Copyright 2012 GridCentric Inc.
URL: http://www.gridcentric.com
Packager: GridCentric Inc. <support@gridcentric.com>
Requires: reactor-client
Requires: python-reactor = %{version}
Requires: python-zookeeper
Requires: python-paste, python-webob1.0
Requires: python-mako, python-pyramid
Requires: python-netifaces, python-ldap
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
/usr/bin/reactor-server
/usr/bin/reactor-defaults
/usr/bin/reactor-dump
/etc/init.d/reactor-server
/etc/logrotate.d/reactor-server
/etc/cron.hourly/clean-zk-logs
/etc/reactor/server.conf
/etc/reactor/example
/etc/reactor/default

%post
if [ "$1" = "1" ]; then
    chkconfig reactor-server on
    service reactor-server start
else
    service reactor-server restart
fi

%preun
if [ "$1" = "0" ]; then
    service reactor-server stop
    chkconfig reactor-server off
fi

%changelog
* Tue Apr 23 2012 Adin Scannell <adin@scannell.ca>
- Create package
