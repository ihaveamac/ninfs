# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from ctypes import windll
import winreg
from argparse import ArgumentParser

SendMessageTimeoutW = windll.user32.SendMessageTimeoutW

HWND_BROADCAST = 0xFFFF
WM_WININICHANGE = 0x001A
SMTO_NORMAL = 0


def refresh_environment():
    res = SendMessageTimeoutW(HWND_BROADCAST, WM_WININICHANGE, 0, 'Environment', SMTO_NORMAL, 10, 0)
    print('SendMessageTimeoutW:', res)


def do(op: str, path: str):
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_ALL_ACCESS)
    value, keytype = winreg.QueryValueEx(k, 'Path')

    paths: 'list[str]' = value.strip(';').split(';')
    refresh = False
    if op == 'add':
        if path not in paths:
            paths.append(path)
            refresh = True
        else:
            print('Already in Path, not adding')
    elif op == 'remove':
        try:
            paths.remove(path)
            refresh = True
        except ValueError:
            pass
    elif op == 'list':
        for path in paths:
            print(path)

    winreg.CloseKey(k)
    if refresh:
        refresh_environment()


if __name__ == '__main__':
    parser = ArgumentParser(description=r'Modify Path inside HKCU\Environment')
    #parser.add_argument('-allusers', help='Modify HKLM (PATH for all users)')
    opers = parser.add_mutually_exclusive_group(required=True)
    opers.add_argument('-add', metavar='PATH', help='Add path')
    opers.add_argument('-remove', metavar='PATH', help='Remove path')
    opers.add_argument('-list', help='List paths (user environment only)', action='store_true')

    args = parser.parse_args()

    if args.add:
        do('add', args.add)
    elif args.remove:
        do('remove', args.remove)
    elif args.list:
        do('list', '')
