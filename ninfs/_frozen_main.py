# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from sys import path, executable
from os.path import dirname, join

# this assumes it's cx_Freeze doing it
# feels like there's a better way, but...
path.insert(0, join(dirname(executable), 'lib', 'ninfs'))

from main import gui
gui()
