#!/usr/bin/env python3

from importlib import import_module
from sys import exit, argv, path
from os.path import basename, dirname, realpath

try:
    from . import __version__
except ImportError:
    try:
        from __init__ import __version__
    except ImportError:
        __version__ = '<unset>'

mount_types = ('cci', 'cdn', 'cia', 'nand', 'ncch', 'romfs', 'sd')

print('fuse-3ds {} - https://github.com/ihaveamac/fuse-3ds'.format(__version__))

def exit_print_types():
    print('Please provide a mount type as the first argument.')
    print(' ', ', '.join(mount_types))
    exit(1)

def mount(mount_type: str) -> int:
    if mount_type not in mount_types:
        exit_print_types()

    module = import_module('mount.' + mount_type)
    return module.main()

def main():
    path.extend(dirname(realpath(__file__)))
    exit(mount(basename(argv[0])[6:].lower()))

if __name__ == '__main__':
    if len(argv) < 2:
        exit_print_types()

    # path fun times
    path.extend(dirname(realpath(__file__)))
    exit(mount(argv.pop(1).lower()))
