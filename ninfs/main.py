#!/usr/bin/env python3

# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from importlib import import_module
from inspect import cleandoc
from os import environ, makedirs
from os.path import basename, dirname, expanduser, join as pjoin, realpath
from sys import exit, argv, path, platform, hexversion, version_info

_path = dirname(realpath(__file__))
if _path not in path:
    path.insert(0, _path)

import mountinfo

windows = platform in {'win32', 'cygwin'}

python_cmd = 'py -3' if windows else 'python3'

if hexversion < 0x030601F0:
    exit('Python {0[0]}.{0[1]}.{0[2]} is not supported. Please use Python 3.6.1 or later.'.format(version_info))


def exit_print_types():
    print('Please provide a mount type as the first argument.')
    print('Available mount types:')
    print()
    for cat, items in mountinfo.categories.items():
        print(cat)
        for item in items:
            info = mountinfo.get_type_info(item)
            print(f' - {item}: {info["name"]} ({info["info"]})')
    exit(1)


def mount(mount_type: str, return_doc: bool = False) -> int:
    if mount_type in {'gui', 'gui_i_want_to_be_an_admin_pls'}:
        from gui import start_gui
        return start_gui()

    if mount_type in {'-v', '--version'}:
        # this kinda feels wrong...
        from __init__ import __version__
        pyver = '{0[0]}.{0[1]}.{0[2]}'.format(version_info)
        if version_info[3] != 'final':
            pyver += '{0[3][0]}{0[4]}'.format(version_info)
        # this should stay as str.format so it runs on older versions
        print('ninfs v{0} on Python {1} - https://github.com/ihaveamac/ninfs'.format(__version__, pyver))
        return 0

    # noinspection PyProtectedMember
    from pyctr.crypto import BootromNotFoundError

    if windows:
        from ctypes import windll, get_last_error

        if windll.shell32.IsUserAnAdmin():
            print('- Note: This should *not* be run as an administrator.',
                  '- The mount will not be normally accessible.',
                  '- This should be run from a non-administrator command prompt or PowerShell prompt.', sep='\n')

        # this allows for the gui parent process to send signal.CTRL_BREAK_EVENT and for this process to receive it
        try:
            import os
            parent_pid = int(environ['NINFS_GUI_PARENT_PID'])
            if windll.kernel32.AttachConsole(parent_pid) == 0:  # ATTACH_PARENT_PROCESS
                print(f'Failed to do AttachConsole({parent_pid}):', get_last_error())
                print("(Note: this most likely isn't the cause of any other issues you might have!)")
        except KeyError:
            pass

    if mount_type not in mountinfo.types and mount_type not in mountinfo.aliases:
        exit_print_types()

    module = import_module('mount.' + mountinfo.aliases.get(mount_type, mount_type))
    if return_doc:
        # noinspection PyTypeChecker
        return module.__doc__

    prog = None
    if __name__ != '__main__':
        prog = 'mount_' + mountinfo.aliases.get(mount_type, mount_type)
    try:
        # noinspection PyUnresolvedReferences
        return module.main(prog=prog)
    except BootromNotFoundError as e:
        print('Bootrom could not be found.',
              'Please read the README of the repository for more details.',
              'Paths checked:',
              *(' - {}'.format(x) for x in e.args[0]), sep='\n')
        return 1
    except RuntimeError as e:
        if e.args == (1,):
            pass  # assuming failed to mount and the reason would be displayed in the terminal


def create_desktop_entry(prefix: str = None):
    desktop_file = cleandoc('''
    [Desktop Entry]
    Name=ninfs
    Comment=Mount Nintendo contents
    Exec=python3 -mninfs gui
    Terminal=true
    Type=Application
    Icon=ninfs
    Categories=Utility;
    ''')
    if not prefix:
        home = expanduser('~')
        prefix = environ.get('XDG_DATA_HOME', pjoin(home, '.local', 'share'))

    app_dir = pjoin(prefix, 'applications')
    makedirs(app_dir, exist_ok=True)

    with open(pjoin(app_dir, 'ninfs.desktop'), 'w', encoding='utf-8') as o:
        print('Writing', o.name)
        o.write(desktop_file)

    for s in ('1024x1024', '128x128', '64x64', '32x32', '16x16'):
        img_dir = pjoin(prefix, 'icons', 'hicolor', s, 'apps')
        makedirs(img_dir, exist_ok=True)
        with open(pjoin(dirname(__file__), 'gui/data', s + '.png'), 'rb') as i, \
                open(pjoin(img_dir, 'ninfs.png'), 'wb') as o:
            print('Writing', o.name)
            o.write(i.read())


def main():
    exit(mount(basename(argv[0])[6:].lower()))


def gui(_allow_admin: bool = False):
    if len(argv) < 2 or argv[1] in {'gui', 'gui_i_want_to_be_an_admin_pls'}:
        from gui import start_gui
        exit(start_gui())
    else:
        exit(mount(argv.pop(1).lower()))


if __name__ == '__main__':
    # path fun times

    if len(argv) < 2:
        exit_print_types()

    exit(mount(argv.pop(1).lower()))
