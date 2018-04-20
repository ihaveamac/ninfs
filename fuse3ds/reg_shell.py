from sys import executable
from os import remove
from os.path import abspath, dirname
from subprocess import Popen
from tempfile import NamedTemporaryFile

base = r'''Windows Registry Editor Version 5.00

[HKEY_CLASSES_ROOT\*\shell\Mount with fuse-3ds\command]
@="\"{exec}\" {extra} gui \"%1\""
'''

base_del = r'''Windows Registry Editor Version 5.00

[-HKEY_CLASSES_ROOT\*\shell\Mount with fuse-3ds]
'''


def call_regedit(data: str):
    # i know this is not very nice
    t = NamedTemporaryFile('w', delete=False, encoding='cp1252', suffix='-fuse3ds.reg')
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
