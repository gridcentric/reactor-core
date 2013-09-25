import os

def read_pid(pid_file):
    if os.path.exists(pid_file):
        pid_file = open(pid_file, 'r')
        pid = pid_file.readline().strip()
        pid_file.close()
        return int(pid)
    else:
        return None
