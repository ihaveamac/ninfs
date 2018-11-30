#!/usr/bin/env python3

import sys

from setuptools import setup, find_packages

if sys.hexversion < 0x030601f0:
    sys.exit('Python 3.6.1+ is required.')

with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()

setup(
    name='fuse-3ds',
    version='1.3.1',
    packages=find_packages(),
    url='https://github.com/ihaveamac/fuse-3ds',
    license='MIT',
    author='Ian Burgwin',
    author_email='ian@ianburgwin.net',
    description='FUSE Filesystem Python scripts for Nintendo 3DS files',
    long_description=readme,
    long_description_content_type='text/markdown',
    package_data={'fuse3ds': ['data/*.png', 'data/*.ico']},
    classifiers=[
        'Topic :: Utilities',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    install_requires=['pycryptodomex'],
    # fusepy should be added here once the main repo has a new release with Windows support.
    extras_require={'gui': ['appJar>=0.93']},
    entry_points={'console_scripts': ['fuse3ds = fuse3ds.main:gui',
                                      # not putting in gui_scripts since the cmd window is required and trying to
                                      # remove it breaks some other stuff with subprocess management ?!?
                                      'mount_cci = fuse3ds.main:main',
                                      'mount_cdn = fuse3ds.main:main',
                                      'mount_cia = fuse3ds.main:main',
                                      'mount_exefs = fuse3ds.main:main',
                                      'mount_nand = fuse3ds.main:main',
                                      'mount_nanddsi = fuse3ds.main:main',
                                      'mount_ncch = fuse3ds.main:main',
                                      'mount_romfs = fuse3ds.main:main',
                                      'mount_sd = fuse3ds.main:main',
                                      'mount_srl = fuse3ds.main:main',
                                      'mount_threedsx = fuse3ds.main:main',
                                      'mount_titledir = fuse3ds.main:main',
                                      # aliases
                                      'mount_3ds = fuse3ds.main:main',
                                      'mount_3dsx = fuse3ds.main:main',
                                      'mount_app = fuse3ds.main:main',
                                      'mount_csu = fuse3ds.main:main',
                                      'mount_cxi = fuse3ds.main:main',
                                      'mount_cfa = fuse3ds.main:main',
                                      'mount_nds = fuse3ds.main:main',]}
)
