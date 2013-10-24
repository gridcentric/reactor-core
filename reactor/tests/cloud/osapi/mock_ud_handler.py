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

"""Not really a mock handler but rather a cut/paste import of the real deal.
This is the code that runs on the cloud-init guest service when passing user
data. Specifically: cloud-init-0.6.3-0ubuntu1.4,
/usr/share/pyshared/cloudinit/UserDataHandler.py."""

import email
from email.mime.base import MIMEBase

def message_from_string(data, headers=None):
    if headers is None:
        headers = {}
    if "mime-version:" in data[0:4096].lower():
        msg = email.message_from_string(data)
        for (key, val) in headers.items():
            if key in msg:
                msg.replace_header(key, val)
            else:
                msg[key] = val
    else:
        mtype = headers.get("Content-Type", "text/x-not-multipart")
        maintype, subtype = mtype.split("/", 1)
        msg = MIMEBase(maintype, subtype, *headers)
        msg.set_payload(data)

    return(msg)

def walk_userdata(istr, callback, data=None):
    partnum = 0
    for part in message_from_string(istr).walk():
        # multipart/* are just containers
        if part.get_content_maintype() == 'multipart':
            continue

        ctype = part.get_content_type()
        if ctype is None:
            ctype = 'application/octet-stream'

        filename = part.get_filename()
        if not filename:
            filename = 'part-%03d' % partnum

        callback(data, ctype, filename, part.get_payload(decode=True))

        partnum = partnum + 1
