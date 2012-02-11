#!/usr/bin/env python

import errno
import logging
import os
import socket
import subprocess
import time

def log():
    logger = logging.getLogger("agent")
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler("/var/log/gc-agent.log")

    handler.setFormatter(logging.Formatter('%(asctime)-6s (%(name)s,  %(levelname)s): %(message)s'))
    
    logger.addHandler(handler)
    return logger

def main():
    logger = log()
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
        logger.info("Error occured when trying to determine ip address. Will run dhclient.")
        subprocess.call(['dhclient','eth0'])
    finally:
        s.close()

    if my_ip_address != ip_address:
        # My ip_address has changed!
        logger.info("ip address changed from %s -> %s. Notifying pancake." %(my_ip_address, ip_address))
        my_ip_address = ip_address
        f = file(ip_filename,'w')
        f.write(my_ip_address)
        f.flush()
        f.close()

        subprocess.call(['curl','http://dscannell-desktop.gridcentric.ca:8080/gridcentric/pancake/new-ip/%s' %(my_ip_address)])

    
while True:
    main()
    time.sleep(1)
