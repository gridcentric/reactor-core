#!/usr/bin/env python

import errno
import os
import socket
import subprocess
import time


def main():
    my_ip_address = ""

    try:
        os.makedirs('/var/cache/gridcentric')
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise e

    ip_filename = ('/var/cache/gridcentric/ip')

    f = None
    try:
        f = file(ip_filename,'r')
        my_ip_address = f.readline()
    except:
        pass
    finally:
        if f != None:
            f.close()

    ip_address = None
    try:
        s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.connect(("dscannell-desktop.gridcentric.ca",22))
        ip_address = s.getsockname()[0]
    except:
        subprocess.call(['dhclient','eth0'])
    finally:
        s.close()

    if my_ip_address != ip_address:
        # My ip_address has changed!
        print "IP address has changed."
        my_ip_address = ip_address
        file(ip_filename,'w').write(my_ip_address)

        subprocess.call(['curl','http://dscannell-desktop.gridcentric.ca:8080/gridcentric/scalemanager/new-ip/%s' %(my_ip_address)])

    

while True:
    main()
    time.sleep(1)
