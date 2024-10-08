# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from os.path import dirname, realpath
from sys import argv, exit, path

# path fun times
path.insert(0, dirname(realpath(__file__)))

from main import exit_print_types, mount, print_version
if len(argv) < 2:
    print_version()
    exit_print_types()

exit(mount(argv.pop(1).lower()))
