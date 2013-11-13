# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from email import message_from_string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from reactor.cloud.osapi.connection import BaseOsConnection
from reactor.cloud.osapi.connection import REACTOR_PRE_SCRIPT
from reactor.cloud.osapi.connection import REACTOR_POST_SCRIPT

def walk_userdata(input):
    """This mocks the code that runs on the cloud-init guest service when
       passing user data."""

    if "mime-version:" in input[0:4096].lower():
        msg = message_from_string(input)
    else:
        msg = MIMEText(input, _subtype = 'x-not-multipart')

    parts = []
    count = 0

    for part in msg.walk():
        if part.get_content_maintype() != 'multipart':
            parttype = part.get_content_type() or 'application/octet-stream'
            filename = part.get_filename() or 'part-%03d' % count
            count += 1
            parts.append((parttype, filename, part.get_payload(decode=True)))

    return parts

fake_name = 'test-cloud-init'
fake_url = 'http://test.gc.ca'

def test_basic_cloud_init():
    conn = BaseOsConnection(fake_name, this_url=fake_url)

    # What will cloud-init see. Note: single script results in "not multipart"
    expect = [
        ('text/x-shellscript', 'part-000',
            REACTOR_PRE_SCRIPT % {
                'url': fake_url,
            }),
        ('text/x-shellscript', 'part-001',
            REACTOR_POST_SCRIPT % {
                'url': fake_url,
                'timeout': 300
            }),
    ]

    assert walk_userdata(conn._user_data()) == expect

def test_cloud_init_user_script():
    script = "#/bin/sh\ntouch /tmp/foo"
    conn = BaseOsConnection(fake_name, this_url=fake_url)

    expect = [
        ('text/x-shellscript', 'part-000',
            REACTOR_PRE_SCRIPT % {
                'url': fake_url,
            }),
        ('text/plain', 'part-001', script),
        ('text/x-shellscript', 'part-002',
            REACTOR_POST_SCRIPT % {
                'url': fake_url,
                'timeout': 300
            }),
    ]

    assert walk_userdata(conn._user_data(script)) == expect

def test_cloud_init_user_multipart():
    # http://cloudinit.readthedocs.org/en/latest/topics/examples.html
    cc = """#cloud-config
#
# This is an example file to automatically configure resolv.conf when the
# instance boots for the first time.
#
# Ensure that your yaml is valid and pass this as user-data when starting
# the instance. Also be sure that your cloud.cfg file includes this
# configuration module in the appropirate section.
#
manage-resolv-conf: true

resolv_conf:
  nameservers: ['8.8.4.4', '8.8.8.8']
  searchdomains:
    - foo.example.com
    - bar.example.com
  domain: example.com
  options:
    rotate: true
    timeout: 1"""

    # https://help.ubuntu.com/community/CloudInit
    bh = """#!/bin/sh
echo "Hello World!"
echo "This will run as soon as possible in the boot sequence"
"""

    conn = BaseOsConnection(fake_name, this_url = fake_url)

    # Create a mime multipart monster
    msg = MIMEMultipart()
    msg.attach(MIMEText(cc, _subtype = "cloud-config"))
    msg.attach(MIMEText(bh, _subtype = "cloud-boothook"))

    expect = [
        ('text/x-shellscript', 'part-000',
            REACTOR_PRE_SCRIPT % {
                'url': fake_url,
            }),
        ('text/cloud-config', 'part-001', cc),
        ('text/cloud-boothook', 'part-002', bh),
        ('text/x-shellscript', 'part-003',
            REACTOR_POST_SCRIPT % {
                'url': fake_url,
                'timeout': 300
            }),
    ]

    assert walk_userdata(conn._user_data(msg.as_string())) == expect
