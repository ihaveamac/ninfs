# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from ctypes import windll
from os.path import isdir, expandvars
from sys import stderr
import winreg
from argparse import ArgumentParser

SendMessageTimeoutW = windll.user32.SendMessageTimeoutW

HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_NORMAL = 0


def refresh_environment():
    res = SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment', SMTO_NORMAL, 10, 0)
    if not res:
        print('Failed to tell explorer about the updated environment.')
        print('SendMessageTimeoutW:', res)


def do(op: str, mypath: str, allusers: bool):
    access = winreg.KEY_READ
    if op in {'add', 'remove'}:
        access |= winreg.KEY_WRITE
    if allusers:
        key = winreg.HKEY_LOCAL_MACHINE
        sub_key = r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
    else:
        key = winreg.HKEY_CURRENT_USER
        sub_key = 'Environment'
    try:
        k = winreg.OpenKey(key, sub_key, 0, access)
    except PermissionError as e:
        print('This program needs to be run as administrator to edit environment variables for all users.', file=stderr)
        print(f'{type(e).__name__}: {e}', file=stderr)
        return
    value, keytype = winreg.QueryValueEx(k, 'Path')

    paths: 'list[str]' = value.strip(';').split(';')
    update = False
    if op == 'add':
        if mypath not in paths:
            paths.append(mypath)
            update = True
        else:
            print('Already in Path, not adding')
    elif op == 'remove':
        try:
            paths.remove(mypath)
            update = True
        except ValueError:
            print('Not in Path')
    elif op == 'list':
        for path in paths:
            print(path)
    elif op == 'check':
        for idx, path in enumerate(paths):
            print(f'{idx}: {path}')
            expanded = expandvars(path)
            if expanded != path:
                print(f'  {expanded}')
            if not isdir(expanded):
                print('  not a directory')

    if update:
        winreg.SetValueEx(k, 'Path', 0, keytype, ';'.join(paths))
    winreg.CloseKey(k)
    if update:
        refresh_environment()


if __name__ == '__main__':
    parser = ArgumentParser(description=r'Modify Path environment variable')
    parser.add_argument('-allusers', help='Modify HKLM (Path for all users), defaults to HKCU (Path for current user)', action='store_true')
    opers = parser.add_mutually_exclusive_group(required=True)
    opers.add_argument('-add', metavar='PATH', help='Add path')
    opers.add_argument('-remove', metavar='PATH', help='Remove path')
    opers.add_argument('-list', help='List paths', action='store_true')
    opers.add_argument('-check', help='Check paths', action='store_true')

    args = parser.parse_args()

    if args.add:
        do('add', args.add, args.allusers)
    elif args.remove:
        do('remove', args.remove, args.allusers)
    elif args.list:
        do('list', '', args.allusers)
    elif args.check:
        do('check', '', args.allusers)
