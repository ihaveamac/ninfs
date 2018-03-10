#!/usr/bin/env python3

import importlib
import sys

mount_types = ('cci', 'cdn', 'cia', 'nand', 'ncch', 'romfs', 'sd')

def print_types():
    print('Please provide a mount type as the first argument.')
    print(' ', ', '.join(mount_types))

if len(sys.argv) < 2:
    print_types()
    sys.exit(1)

mount_type = sys.argv[1].lower()
if mount_type not in mount_types:
    print_types()
    sys.exit(1)

module = importlib.import_module('fuse3ds.mount.' + mount_type)
del sys.argv[1]
sys.exit(module.main())
