Name: python-reactor
Summary: Reactor python bindings
Version: %{version}
Release: 1
Group: System
License: Copyright 2012 GridCentric Inc.
URL: http://www.gridcentric.com
Packager: GridCentric Inc. <support@gridcentric.com>
BuildRoot: %{_tmppath}/%{name}.%{version}-buildroot
Requires: python-httplib2
AutoReq: no
AutoProv: no

# see Trac ticket #449
%global _binary_filedigest_algorithm 1
# Don't strip the binaries.
%define __os_install_post %{nil}

%description
Reactor python bindings.

%install
true

%files
/usr/

%changelog
* Tue Apr 23 2012 Adin Scannell <adin@scannell.ca>
- Create package
