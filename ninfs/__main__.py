# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from os.path import dirname, realpath
from sys import argv, exit, path, version_info

# path fun times
path.insert(0, dirname(realpath(__file__)))

from main import exit_print_types, mount
if len(argv) < 2:
    exit_print_types()

if argv[1] == '--install-desktop-entry':
    from main import create_desktop_entry
    prefix = None if len(argv) < 3 else argv[2]
    create_desktop_entry(prefix)
    exit(0)

if argv[1] in {'-V', '--version'}:
    # this kinda feels wrong...
    from __init__ import __version__
    pyver = '{0[0]}.{0[1]}.{0[2]}'.format(version_info)
    if version_info[3] != 'final':
        pyver += '{0[3][0]}{0[4]}'.format(version_info)
    # this should stay as str.format so it runs on older versions
    print('ninfs v{0} on Python {1} - https://github.com/ihaveamac/ninfs'.format(__version__, pyver))
    exit(0)

exit(mount(argv.pop(1).lower()))
