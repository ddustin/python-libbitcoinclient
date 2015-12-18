from setuptools import setup

setup(
    name='python-libbitcoinclient',
    version="0.3.1",
    install_requires=['twisted', 'ecdsa', 'pyzmq'],
    packages=['obelisk'],
    maintainer='Chris Pacia',
    maintainer_email='chris@ob1.io',
    zip_safe=False,
    description="Python native client for the libbitcoin blockchain server.",
    long_description=open('README.txt').read(),
    license='GNU Affero General Public License',
    keywords='bitcoin blockchain libbitcoin query transaction federated',
    url='https://github.com/OpenBazaar/python-libbitcoinclient'
)
