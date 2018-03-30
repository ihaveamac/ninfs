#!/usr/bin/env python3

import sys

from setuptools import setup

if sys.hexversion < 0x030502f0:
    sys.exit('Python 3.5.2+ is required.')

with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()

install_requires = ['pycryptodomex', 'appJar']
# this should be removed once windows support is in the original fusepy.
if sys.platform not in {'win32', 'cygwin'}:
    install_requires.append('fusepy')

setup(
    name='fuse-3ds',
    version='1.0b4.dev1',
    packages=['fuse3ds', 'fuse3ds.pyctr', 'fuse3ds.mount'],
    url='https://github.com/ihaveamac/fuse-3ds',
    license='MIT',
    author='Ian Burgwin',
    author_email='',
    description='FUSE Filesystem Python scripts for Nintendo 3DS files',
    long_description=readme,
    classifiers=[
        'Topic :: Utilities',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    install_requires=install_requires,
    entry_points={'console_scripts': ['fuse3ds = fuse3ds.main:gui',
                                      # not putting in gui_scripts since the cmd window
                                      # is needed on windows atm.
                                      'mount_cci = fuse3ds.main:main',
                                      'mount_cdn = fuse3ds.main:main',
                                      'mount_cia = fuse3ds.main:main',
                                      'mount_exefs = fuse3ds.main:main',
                                      'mount_nand = fuse3ds.main:main',
                                      'mount_ncch = fuse3ds.main:main',
                                      'mount_romfs = fuse3ds.main:main',
                                      'mount_sd = fuse3ds.main:main',
                                      'mount_titledir = fuse3ds.main:main',
                                      # aliases
                                      'mount_3ds = fuse3ds.main:main',
                                      'mount_cxi = fuse3ds.main:main',
                                      'mount_cfa = fuse3ds.main:main',
                                      'mount_app = fuse3ds.main:main']}
)
