#!/usr/bin/env python3

import sys

from setuptools import setup, find_packages

if sys.hexversion < 0x030601f0:
    sys.exit('Python 3.6.1+ is required.')

with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()

# based on https://github.com/Legrandin/pycryptodome/blob/b3a394d0837ff92919d35d01de9952b8809e802d/setup.py
with open('ninfs/__init__.py', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('__version__'):
            version = eval(line.split('=')[1])

setup(
    name='ninfs',
    version=version,
    packages=find_packages(),
    url='https://github.com/ihaveamac/ninfs',
    license='MIT',
    author='Ian Burgwin',
    author_email='ian@ianburgwin.net',
    description='FUSE filesystem Python scripts for Nintendo console files',
    long_description=readme,
    long_description_content_type='text/markdown',
    package_data={'ninfs.gui': ['data/*.png', 'data/*.ico', 'data/licenses/*']},
    classifiers=[
        'Topic :: Utilities',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    install_requires=['pycryptodomex==3.9.8', 'pyctr==0.4.5', 'haccrypto==0.1.0'],
    python_requires='>=3.6.1',
    # fusepy should be added here once the main repo has a new release with Windows support.
    entry_points={'gui_scripts': ['ninfsw = ninfs.main:gui'],
                  'console_scripts': ['ninfs = ninfs.main:gui',
                                      # not putting in gui_scripts since the cmd window is required and trying to
                                      # remove it breaks some other stuff with subprocess management ?!?
                                      'mount_cci = ninfs.main:main',
                                      'mount_cdn = ninfs.main:main',
                                      'mount_cia = ninfs.main:main',
                                      'mount_exefs = ninfs.main:main',
                                      'mount_nandctr = ninfs.main:main',
                                      'mount_nandtwl = ninfs.main:main',
                                      'mount_nandhac = ninfs.main:main',
                                      'mount_ncch = ninfs.main:main',
                                      'mount_romfs = ninfs.main:main',
                                      'mount_sd = ninfs.main:main',
                                      'mount_srl = ninfs.main:main',
                                      'mount_threedsx = ninfs.main:main',
                                      # aliases
                                      'mount_3ds = ninfs.main:main',
                                      'mount_3dsx = ninfs.main:main',
                                      'mount_app = ninfs.main:main',
                                      'mount_csu = ninfs.main:main',
                                      'mount_cxi = ninfs.main:main',
                                      'mount_cfa = ninfs.main:main',
                                      'mount_nand = ninfs.main:main',
                                      'mount_nanddsi = ninfs.main:main',
                                      'mount_nandswitch = ninfs.main:main',
                                      'mount_nandnx = ninfs.main:main',
                                      'mount_nds = ninfs.main:main']}
)
