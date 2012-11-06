import os
from setuptools import setup

def all_files(path):
    found = {}
    for root, dirs, files in os.walk(path):
        package = root.replace('/', '.')
        found[package] = files
    return found

# Index all the administration console files.
admin_files = all_files('reactor/admin')

setup(
    name="reactor-server",
    version='1.0',
    author='Gridcentric Inc.',
    author_email='info@gridcentric.com',
    url='http://www.gridcentric.com',
    packages=[
        'reactor'
    ] + admin_files.keys(),
    description='Reactor virtual appliance server.',
    package_data = admin_files,
    entry_points={
        'console_scripts': [
            'reactor-server = reactor.server:main',
            'reactor = pancake.cli:main'
        ]
    },
)

print all_files('reactor/admin')
