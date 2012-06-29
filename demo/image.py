#!/usr/bin/env python

import sys
import os
import tempfile
import shutil
import atexit

def save(filenames):
    f = open('image_data.py', 'w')

    # Generate image_data.py.
    for filename in filenames:
        img = open(filename, 'r')
        data = img.read()
        img.close()

        f.write("%s = '" % os.path.basename(filename).split(".")[0])
        for x in data:
            f.write("\\x%02x" % ord(x))
        f.write("'\n")
    f.close()

def load():
    # Import our generated image_data.
    import image_data

    dirname = tempfile.mkdtemp()
    for img in dir(image_data):
        if img[0] == '_':
            continue

        data = getattr(image_data, img)
        f = open(os.path.join(dirname, img) + ".png", 'w')
        f.write(data)
        f.close()

    def clean():
        shutil.rmtree(dirname)
    atexit.register(clean)

    return dirname

def main():
    save(sys.argv[1:])

if __name__ == "__main__":
    main()
