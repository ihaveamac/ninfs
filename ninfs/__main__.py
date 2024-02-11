# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from os.path import dirname, realpath
from sys import argv, exit, path

if 'nix_run_setup' in argv:
    # I don't understand why this gets called with nix build!
    # This feels like a hack but I currently don't know a better solution.
    print('nix build is calling me! (__main__)')
    exit(0)

# path fun times
path.insert(0, dirname(realpath(__file__)))

from main import exit_print_types, mount, print_version
if len(argv) < 2:
    print_version()
    exit_print_types()

if argv[1] == '--install-desktop-entry':
    from main import create_desktop_entry
    prefix = None if len(argv) < 3 else argv[2]
    create_desktop_entry(prefix)
    exit(0)

exit(mount(argv.pop(1).lower()))
