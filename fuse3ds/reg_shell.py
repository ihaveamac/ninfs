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


def add_reg(_pyi: bool):
    fmtmap = {'exec': executable.replace('\\', '\\\\'), 'extra': ''}
    if not _pyi:
        fmtmap['extra'] = r'\"{}\"'.format(dirname(abspath(__file__)).replace('\\', '\\\\'))
    # i know this is not very nice
    result = base.format_map(fmtmap).replace('\n', '\r\n')

    t = NamedTemporaryFile(delete=False)
    try:
        t.write(result.encode('cp1252'))
        t.close()  # need to close so regedit can open it
        p = Popen(['regedit.exe', t.name], shell=True)
        p.wait()
    finally:
        t.close()  # just in case
        remove(t.name)


def del_reg():
    t = NamedTemporaryFile(delete=False)
    try:
        t.write(base_del.encode('cp1252'))
        t.close()  # need to close so regedit can open it
        p = Popen(['regedit.exe', t.name], shell=True)
        p.wait()
    finally:
        t.close()  # just in case
        remove(t.name)
