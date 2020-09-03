# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import platform
import sys


def get_os_ver():
    if sys.platform == 'win32':
        import winreg

        ver = platform.win32_ver()
        marketing_ver = ver[0]
        service_pack = ver[2]

        os_ver = 'Windows ' + marketing_ver
        if marketing_ver == '10':
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows NT\CurrentVersion')
            try:
                r = winreg.QueryValueEx(k, 'ReleaseId')[0]
            except FileNotFoundError:
                r = '1507'  # assuming RTM, since this key only exists in 1511 and up
            os_ver += ', version ' + r
        else:
            if service_pack != 'SP0':
                os_ver += ' ' + service_pack
    elif sys.platform == 'darwin':
        ver = platform.mac_ver()
        os_ver = f'macOS {ver[0]} on {ver[2]}'
    else:
        ver = platform.uname()
        os_ver = f'{ver.system} {ver.release} on {ver.machine}'

    return os_ver
