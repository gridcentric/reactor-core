#!/bin/bash
# Install the Reactor server in an Ubuntu or Centos6 environment.
# Can be run interactively:
#   sudo bash setup-server.sh
# Or passed to an instance via cloud-init:
#   nova boot ... --user-data setup-server.sh ...

set -x
set -e

KEYFILE=$(mktemp)

cleanup() {
    rm -f $KEYFILE
}
trap cleanup EXIT

# This is the GPG Gridcentric package signing public key.
cat >$KEYFILE <<EOF
-----BEGIN PGP PUBLIC KEY BLOCK-----
Version: GnuPG v1.4.11 (GNU/Linux)

mQENBFAQqgUBCADOMIkW4BliIOZyks8addo/SJjXRVjbAs2/O5pINHTRRo8DabCB
ISbKAjmxpkepQ/mN2o4cxK+3IGpSVQhrhLRyBRRMZv1MH4n+Yoq2AemO83ILQthi
39jHwKm107untAeLKTwt1DSY1HnFEQJl5bwG7HHqz3iD9HCwY5bX4eDrm4AxW0NG
rPdZpnLcuZfgMWEzRnhSkaTrCKiysQs5BVF3twbmzgO6hK26XjEOCNeOgHWGAbjZ
tky9zcjg2c1FG6g7pYyPyeLkSpF+CfhYe5pclrSvB708wVb+NczBD9MfInV9Er9/
UYr2kd4rYttc/tUFSCPjKoT9grO7dtIHbZVtABEBAAG0J0dyaWRjZW50cmljIElu
Yy4gPGluZm9AZ3JpZGNlbnRyaWMuY29tPokBOAQTAQIAIgUCUBCqBQIbAwYLCQgH
AwIGFQgCCQoLBBYCAwECHgECF4AACgkQ9sSiVmboP0x1eAgAkpUEzJ5ZxjZPxbPH
de5ryZpUvb/3VKsXiV6mRPHM78Psdjc68dnm3n1V57g5zc57n2mD/li80Y+bqzgk
eWjMg6JRr1bBIgz2kKVtXQhmDWsk9tu3KW3AieVArsZWjGo8Oab4jNZO0gq2QOcR
Bt/uTYW2wU9xO0S/AyRtwBUqjDP7Q9LKp2i5UrBCtQfXQ1WFvUgQzhcYwFkoO/oH
bi4S4hcMsGBQjsrtQkorwj8Fp3QuUErvjnjT6+6RqO+W2SjYb7eFSBBHRD6Wnas4
TDETaIfuEOonLXzRjaQ2QTprVIZDQkY9Qnp/BZXfWheXeIkq6jsWyV87Wmwm+V8e
zGdl0Q==
=DHFj
-----END PGP PUBLIC KEY BLOCK-----
EOF

# Detect distro by finding out how core utils are provided.
if dpkg -l coreutils >/dev/null 2>&1; then

    # Import the package key and add repos.
    apt-key add $KEYFILE
    cat >/etc/apt/sources.list.d/reactor.list <<-EOF
	deb http://downloads.gridcentric.com/packages/reactor/reactor-core/precise gridcentric multiverse
	deb http://downloads.gridcentric.com/packages/cobaltclient/grizzly/precise gridcentric multiverse
	EOF

    # Add Ubuntu Cloud Archive repo for novaclient
    add-apt-repository -y cloud-archive:havana

    # Update all repos.
    apt-get update

    # Install novaclient here.
    apt-get -y install ubuntu-cloud-keyring
    apt-get -y install python-novaclient

    # Install zookeeper here.
    apt-get -y install zookeeperd

    # Install all packages.
    # (Deb packages come with soft dependencies).
    apt-get -y -o APT::Install-Recommends=1 install reactor-server
    apt-get -y -o APT::Install-Recommends=1 install reactor-manager

elif rpm -ql coreutils >/dev/null 2>&1; then

    # Import the package key and add repos.
    rpm --import $KEYFILE
    cat >/etc/yum.repos.d/reactor.repo <<-EOF
	[reactor]
	name=Gridcentric Reactor
	baseurl=http://downloads.gridcentric.com/packages/reactor/reactor-core/centos/
	gpgcheck=1
	enabled=1

	[cobaltclient]
	name=Cobalt Extension for novaclient
	baseurl=http://downloads.gridcentric.com/packages/cobaltclient/grizzly/centos/
	gpgcheck=1
	enabled=1
	EOF

    # Add requisite EPEL repos, if not already installed.
    # This is the EPEL public key. You can verify at
    # https://fedoraproject.org/static/0608B895.txt
    cat >$KEYFILE <<-EOF
	-----BEGIN PGP PUBLIC KEY BLOCK-----
	Version: GnuPG v1.4.5 (GNU/Linux)

	mQINBEvSKUIBEADLGnUj24ZVKW7liFN/JA5CgtzlNnKs7sBg7fVbNWryiE3URbn1
	JXvrdwHtkKyY96/ifZ1Ld3lE2gOF61bGZ2CWwJNee76Sp9Z+isP8RQXbG5jwj/4B
	M9HK7phktqFVJ8VbY2jfTjcfxRvGM8YBwXF8hx0CDZURAjvf1xRSQJ7iAo58qcHn
	XtxOAvQmAbR9z6Q/h/D+Y/PhoIJp1OV4VNHCbCs9M7HUVBpgC53PDcTUQuwcgeY6
	pQgo9eT1eLNSZVrJ5Bctivl1UcD6P6CIGkkeT2gNhqindRPngUXGXW7Qzoefe+fV
	QqJSm7Tq2q9oqVZ46J964waCRItRySpuW5dxZO34WM6wsw2BP2MlACbH4l3luqtp
	Xo3Bvfnk+HAFH3HcMuwdaulxv7zYKXCfNoSfgrpEfo2Ex4Im/I3WdtwME/Gbnwdq
	3VJzgAxLVFhczDHwNkjmIdPAlNJ9/ixRjip4dgZtW8VcBCrNoL+LhDrIfjvnLdRu
	vBHy9P3sCF7FZycaHlMWP6RiLtHnEMGcbZ8QpQHi2dReU1wyr9QgguGU+jqSXYar
	1yEcsdRGasppNIZ8+Qawbm/a4doT10TEtPArhSoHlwbvqTDYjtfV92lC/2iwgO6g
	YgG9XrO4V8dV39Ffm7oLFfvTbg5mv4Q/E6AWo/gkjmtxkculbyAvjFtYAQARAQAB
	tCFFUEVMICg2KSA8ZXBlbEBmZWRvcmFwcm9qZWN0Lm9yZz6JAjYEEwECACAFAkvS
	KUICGw8GCwkIBwMCBBUCCAMEFgIDAQIeAQIXgAAKCRA7Sd8qBgi4lR/GD/wLGPv9
	qO39eyb9NlrwfKdUEo1tHxKdrhNz+XYrO4yVDTBZRPSuvL2yaoeSIhQOKhNPfEgT
	9mdsbsgcfmoHxmGVcn+lbheWsSvcgrXuz0gLt8TGGKGGROAoLXpuUsb1HNtKEOwP
	Q4z1uQ2nOz5hLRyDOV0I2LwYV8BjGIjBKUMFEUxFTsL7XOZkrAg/WbTH2PW3hrfS
	WtcRA7EYonI3B80d39ffws7SmyKbS5PmZjqOPuTvV2F0tMhKIhncBwoojWZPExft
	HpKhzKVh8fdDO/3P1y1Fk3Cin8UbCO9MWMFNR27fVzCANlEPljsHA+3Ez4F7uboF
	p0OOEov4Yyi4BEbgqZnthTG4ub9nyiupIZ3ckPHr3nVcDUGcL6lQD/nkmNVIeLYP
	x1uHPOSlWfuojAYgzRH6LL7Idg4FHHBA0to7FW8dQXFIOyNiJFAOT2j8P5+tVdq8
	wB0PDSH8yRpn4HdJ9RYquau4OkjluxOWf0uRaS//SUcCZh+1/KBEOmcvBHYRZA5J
	l/nakCgxGb2paQOzqqpOcHKvlyLuzO5uybMXaipLExTGJXBlXrbbASfXa/yGYSAG
	iVrGz9CE6676dMlm8F+s3XXE13QZrXmjloc6jwOljnfAkjTGXjiB7OULESed96MR
	XtfLk0W5Ab9pd7tKDR6QHI7rgHXfCopRnZ2VVQ==
	=V/6I
	-----END PGP PUBLIC KEY BLOCK-----
	EOF
    rpm -qi gpg-pubkey-0608b895-4bd22942 > /dev/null 2>&1 || rpm --import $KEYFILE
    rpm -qa | grep -q epel-release || rpm -Uvh \
            http://dl.fedoraproject.org/pub/epel/6/`uname -m`/epel-release-6-8.noarch.rpm

    # Ugh. The packages on centos are broken for pyramid and zope.
    # This is really annoying. We have to ensure that the current
    # version is up-to-date and then allow easy_install to install
    # an upgraded version.
    yum -y install python-webob1.0
    easy_install webob
    yum -y install python-zope-interface
    easy_install --upgrade zope.interface

    # Install zookeeper here.
    yum -y install zookeeper

    # Loadbalancer soft dependencies.
    yum -y install nginx haproxy dnsmasq socat
    # Cloud connection soft dependencies.
    yum -y install python-novaclient cobalt-novaclient

    # Reactor core (previous packages should be done).
    yum -y install reactor-server
    yum -y install reactor-manager

else
    # Unknown system!
    exit 2
fi

# Save copies of replaced files.
BACKUP_DATE=$(date +%Y%m%d%H%M%S)

# Setup nginx, if it's installed.
if [ -d /etc/nginx ]; then
    # Ensure necessary directories exist.
    mkdir -p /var/log/nginx
    mkdir -p /etc/nginx/conf.d
    mkdir -p /etc/nginx/sites-enabled

    # Clear out the default site, if it's there.
    rm -f /etc/nginx/sites-enabled/default
    rm -f /etc/nginx/conf.d/default.conf

    if [ -f /etc/nginx/nginx.conf ]; then
        # Save the original configuration.
        mv /etc/nginx/nginx.conf /etc/nginx/nginx.conf.$BACKUP_DATE
    fi

    # Install the reactor configuration.
    cp -a /etc/reactor/example/nginx/nginx.conf /etc/nginx/nginx.conf
fi

# Save the haproxy config, if it's installed.
if [ -f /etc/haproxy/haproxy.cfg ]; then
    cp -a /etc/haproxy/haproxy.cfg /etc/haproxy/haproxy.cfg.$BACKUP_DATE
fi

# Check that haproxy is enabled.
if [ -f /etc/default/haproxy ]; then
    if grep ENABLED /etc/default/haproxy >/dev/null; then
        # Ensure that the haproxy init script is enabled.
        sed -e 's/ENABLED=.*/ENABLED=1/' -i /etc/default/haproxy
    fi
fi

# Save the dnsmasq config, if it's installed.
if [ -f /etc/dnsmasq.conf ]; then
    cp -a /etc/dnsmasq.conf /etc/dnsmasq.conf.$BACKUP_DATE
fi

# Important: defaults should only be run for one reactor in a clustered setup.
reactor-defaults
