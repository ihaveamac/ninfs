# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from sys import argv, exit, path, executable
from os.path import dirname, join


# this assumes it's cx_Freeze doing it
# feels like there's a better way, but...
path.insert(0, join(dirname(executable), 'lib', 'ninfs'))

if len(argv) < 2 or argv[1] in {'gui', 'gui_i_want_to_be_an_admin_pls'}:
    from gui import start_gui
    start_gui()
else:
    from main import mount
    exit(mount(argv.pop(1).lower()))
