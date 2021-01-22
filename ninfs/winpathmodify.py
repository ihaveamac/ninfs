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


def add(path: str):
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_ALL_ACCESS)

    value, keytype = winreg.QueryValueEx(k, 'Path')

    paths: list = value.strip(';').split(';')
    if path not in paths:
        paths.append(path)

    winreg.SetValueEx(k, 'Path', 0, keytype, ';'.join(paths))

    winreg.CloseKey(k)

    refresh_environment()


def remove(path: str):
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_ALL_ACCESS)

    value, keytype = winreg.QueryValueEx(k, 'Path')

    paths: list = value.strip(';').split(';')
    try:
        paths.remove(path)
    except ValueError:
        pass

    winreg.SetValueEx(k, 'Path', 0, keytype, ';'.join(paths))

    winreg.CloseKey(k)

    refresh_environment()


if __name__ == '__main__':
    parser = ArgumentParser(description=r'Modify Path inside HKCU\Environment')
    parser.add_argument('oper', help='Operation (add, remove)')
    parser.add_argument('path', help='Path to add or remove')

    args = parser.parse_args()

    if args.oper == 'add':
        add(args.path)
    elif args.oper == 'remove':
        remove(args.path)


