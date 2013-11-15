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

import os
import subprocess

def read_pid(pid_file):
    if os.path.exists(pid_file):
        pid_file = open(pid_file, 'r')
        pid = pid_file.readline().strip()
        pid_file.close()
        return int(pid)
    else:
        return None

def binary_exists(binary):
    # Raise an exception if the binary is not installed.
    # This is used at the top level of modules to ensure
    # that they are not-importable if it's not enabled.
    which = subprocess.Popen(
        ["which", binary],
        close_fds=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    which.communicate()

    # Return true if successful.
    return which.returncode == 0
