Name: reactor-agent
Summary: Reactor agent script.
Version: %{version}
Release: 1
Group: System
License: Copyright 2012 GridCentric Inc.
URL: http://www.gridcentric.com
Packager: GridCentric Inc. <support@gridcentric.com>
BuildRoot: %{_tmppath}/%{name}.%{version}-buildroot
Requires: vms-agent
AutoReq: no
AutoProv: no

# see Trac ticket #449
%global _binary_filedigest_algorithm 1
# Don't strip the binaries.
%define __os_install_post %{nil}

%description
Reactor in-guest agent for Virtual Memory Streaming VMs.

%install
rm -rf $RPM_BUILD_ROOT
install -d $RPM_BUILD_ROOT
rsync -rav --delete ../../agent/* $RPM_BUILD_ROOT

%files
/etc/gridcentric/boot.d/90_reactor
/etc/gridcentric/clone.d/90_reactor

%changelog
* Tue Jun 28 2012 Adin Scannell <adin@scannell.ca>
- Create package
