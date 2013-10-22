Name: reactor-client
Summary: Reactor client
Version: %{version}
Release: 1
Group: System
License: Copyright 2012 GridCentric Inc.
URL: http://www.gridcentric.com
Packager: GridCentric Inc. <support@gridcentric.com>
Requires: python-reactor
BuildRoot: %{_tmppath}/%{name}.%{version}-buildroot
AutoReq: no
AutoProv: no

# see Trac ticket #449
%global _binary_filedigest_algorithm 1
# Don't strip the binaries.
%define __os_install_post %{nil}

%description
Reactor client.

%install
true

%files
/

%changelog
* Sun Oct 20 2013 Adin Scannell <adin@scannell.ca>
- Create package
