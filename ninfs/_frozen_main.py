# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import sys
from os.path import dirname, join

if getattr(sys, 'frozen', False):
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller
        pass
    else:
        # cx_Freeze probably
        sys.path.insert(0, join(dirname(sys.executable), 'lib', 'ninfs'))

from main import gui
gui()
