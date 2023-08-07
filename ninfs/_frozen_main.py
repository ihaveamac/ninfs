# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import sys
from os.path import dirname, join
from os import environ

if len(sys.argv) > 1:
    # Ignore `-psn_0_#######` which is added if macOS App Translocation is in effect
    if sys.argv[1].startswith('-psn'):
        del sys.argv[1]

if getattr(sys, 'frozen', False):
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller
        pass
    else:
        # cx_Freeze probably
        sys.path.insert(0, join(dirname(sys.executable), 'lib', 'ninfs'))

        if sys.platform == 'win32':
            # this will try to fix loading tkinter in paths containing non-latin characters
            environ['TCL_LIBRARY'] = 'lib/tkinter/tcl8.6'

from main import gui
gui()
