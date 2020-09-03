# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from subprocess import check_call, CalledProcessError
from sys import platform

is_windows = platform == 'win32'
is_mac = platform == 'darwin'

if is_windows:
    from os import startfile


def open_directory(path: str):
    if is_windows:
        startfile(path)
    elif is_mac:
        try:
            check_call(['/usr/bin/open', '-a', 'Finder', path])
        except CalledProcessError as e:
            return e.returncode
    else:
        # assuming linux for this, feel free to add an exception if another OS has a different method
        try:
            check_call(['xdg-open', path])
        except CalledProcessError as e:
            return e.returncode
