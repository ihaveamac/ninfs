# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from sys import executable
from os import remove
from os.path import abspath, dirname
from subprocess import Popen
from tempfile import NamedTemporaryFile
import winreg

# these do not use winreg due to administrator access being required.
base = r'''Windows Registry Editor Version 5.00

[HKEY_CLASSES_ROOT\*\shell\Mount with ninfs\command]
@="\"{exec}\" {extra} gui \"%1\""

[-HKEY_CLASSES_ROOT\*\shell\Mount with fuse-3ds]
'''

base_del = r'''Windows Registry Editor Version 5.00

[-HKEY_CLASSES_ROOT\*\shell\Mount with ninfs]

[-HKEY_CLASSES_ROOT\*\shell\Mount with fuse-3ds]
'''


def call_regedit(data: str):
    # this does not use winreg due to administrator access being required.
    t = NamedTemporaryFile('w', delete=False, encoding='cp1252', suffix='-ninfs.reg')
    try:
        t.write(data)
        t.close()  # need to close so regedit can open it
        p = Popen(['regedit.exe', t.name], shell=True)
        p.wait()
    finally:
        t.close()  # just in case
        remove(t.name)


def add_reg(_pyi: bool):
    fmtmap = {'exec': executable.replace('\\', '\\\\'), 'extra': ''}
    if not _pyi:
        fmtmap['extra'] = r'\"{}\"'.format(dirname(abspath(__file__)).replace('\\', '\\\\'))
    call_regedit(base.format_map(fmtmap))


def del_reg():
    call_regedit(base_del)


# I'm wondering how I could properly check if this is running as admin, instead of always checking if UAC is disabled
#   if IsUserAnAdmin is 1.
def uac_enabled() -> bool:
    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System', 0,
                         winreg.KEY_READ)
    return bool(winreg.QueryValueEx(key, 'EnableLUA')[0])
