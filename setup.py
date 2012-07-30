from setuptools import setup

setup(
    name="reactor-server",
    version='1.0',
    author='Gridcentric Inc.',
    author_email='info@gridcentric.com',
    url='http://www.gridcentric.com',
    packages=[
        'gridcentric',
        'gridcentric.reactor',
    ],
    description='Reactor virtual appliance server.',
    entry_points={
        'console_scripts': [
            'reactor = gridcentric.reactor.server:main'
        ]
    },
)
