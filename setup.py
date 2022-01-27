#!/usr/bin/env python3

import sys

from setuptools import setup, find_packages

from ninfs import mountinfo

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
    install_requires=['pycryptodomex>=3.9,<4', 'pyctr>=0.5.1,<0.7', 'haccrypto>=0.1', 'pypng>=0.0.21'],
    python_requires='>=3.6.1',
    # fusepy should be added here once the main repo has a new release with Windows support.
    entry_points={'gui_scripts': ['ninfsw = ninfs.main:gui'],
                  'console_scripts': ['ninfs = ninfs.main:gui'] +
                                     [f'mount_{x} = ninfs.main:main' for x in mountinfo.types.keys()] +
                                     [f'mount_{x} = ninfs.main:main' for x in mountinfo.aliases.keys()]}
)
