# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

# not very good with gui development...
# don't read this file, it sucks
print('Importing dependencies...')

import json
import webbrowser
from configparser import ConfigParser
from contextlib import suppress
from glob import iglob
from hashlib import sha256
from os import environ, kill, makedirs, rmdir
from os.path import abspath, dirname, expanduser, getsize, isfile, isdir, ismount, join as pjoin
from shutil import get_terminal_size
from ssl import PROTOCOL_TLSv1_2, SSLContext
from subprocess import Popen, check_call, CalledProcessError
from sys import argv, executable, exit, platform, version_info, maxsize, stderr
from time import sleep
from traceback import print_exc
from typing import TYPE_CHECKING
from urllib.request import urlopen

try:
    from appJar import gui
    from appJar.appjar import ItemLookupError
except ImportError as e:
    print_exc()
    print(file=stderr)
    if 'tk' in e.args[0].lower():
        exit('Could not import tkinter, please install python3-tk (or equivalent for your distribution).')
    else:
        exit('Could not import appJar. If you installed via pip, make sure you installed with the gui.\n'
             'Read the README at the GitHub repository.')
    # this code will never be reached
    gui = ItemLookupError = None

from pkg_resources import parse_version

from __init__ import __version__ as version
from fmt_detect import detect_format
from pyctr.util import config_dirs

if TYPE_CHECKING:
    from http.client import HTTPResponse
    # noinspection PyProtectedMember
    from pkg_resources._vendor.packaging.version import Version
    from typing import Any, Dict, List

windows = platform == 'win32'  # only for native windows, not cygwin
macos = platform == 'darwin'

ITEM = 'item'
EASTWEST = 'ew'
PV = 'previous'
LABEL1 = 'label1'
LABEL2 = 'label2'
LABEL3 = 'label3'
MOUNTPOINT = 'mountpoint'

MOUNT = 'Mount'
UNMOUNT = 'Unmount'
DIRECTORY = 'Directory'
FILE = 'File'
OK = 'OK'

DRAGFILE = 'Drag a file here or browse...'
DRAGDIR = 'Drag a directory here or browse...'
BROWSE = 'Browse...'
ALLOW_OTHER = 'Allow access by other users (-o allow_other)'
ALLOW_ROOT = 'Allow access by root (-o allow_root)'
ALLOW_NONE = "Don't allow other users"

b9_hashes = {
    '2f88744feed717856386400a44bba4b9ca62e76a32c715d4f309c399bf28166f': 'boot9',
    '7331f7edece3dd33f2ab4bd0b3a5d607229fd19212c10b734cedcaf78c1a7b98': 'boot9_prot',
}

b9_paths: 'List[str]' = []
for p in config_dirs:
    b9_paths.append(pjoin(p, 'boot9.bin'))
    b9_paths.append(pjoin(p, 'boot9_prot.bin'))

with suppress(KeyError):
    b9_paths.insert(0, environ['BOOT9_PATH'])

seeddb_paths: 'List[str]' = [pjoin(x, 'seeddb.bin') for x in config_dirs]
with suppress(KeyError):
    seeddb_paths.insert(0, environ['SEEDDB_PATH'])

home = expanduser('~')

# dir to copy to if chosen to copy boot9/seeddb in gui
# config_dir is fuse-3ds because it is the previous name of this project, maybe later I'll support a new ninfs dir
if windows:
    target_dir: str = pjoin(environ.get('APPDATA'), '3ds')
    config_dir: str = pjoin(environ.get('APPDATA'), 'fuse-3ds')
elif macos:
    target_dir: str = pjoin(home, 'Library', 'Application Support', '3ds')
    config_dir: str = pjoin(home, 'Library', 'Application Support', 'fuse-3ds')
else:
    target_dir: str = pjoin(home, '.3ds')
    config_root = environ.get('XDG_CONFIG_HOME')
    if not config_root:
        # check other paths in XDG_CONFIG_DIRS to see if fuse-3ds already exists in one of them
        config_roots: str = environ.get('XDG_CONFIG_DIRS')
        if not config_roots:
            config_roots = '/etc/xdg'
        config_paths = config_roots.split(':')
        for p in config_paths:
            d = pjoin(p, 'fuse-3ds')
            if isdir(d):
                config_root = p
                break
    # check again to see if it was set
    if not config_root:
        config_root = pjoin(home, '.config')
    config_dir = pjoin(config_root, 'fuse-3ds')

makedirs(config_dir, exist_ok=True)
update_config = ConfigParser()

configs = {'update': update_config}


def init_config(kind: str, defaults):
    config_path = pjoin(config_dir, kind + '.cfg')
    if not configs[kind].read(config_path):
        print('Creating new', kind, 'config...')
        configs[kind].update(defaults)
        write_config(kind)
    else:
        print('Loaded', kind, 'config.')


def write_config(kind: str, section=None, option=None, value=None):
    config_path = pjoin(config_dir, kind + '.cfg')
    if section:
        configs[kind][section][option] = str(value)
    try:
        with open(config_path, 'w', encoding='utf-8') as o:
            configs[kind].write(o)
            print('Wrote', kind, 'config to', config_path)
            return True
    except Exception:
        print_exc()
        print()
        print('Failed to write', kind, 'config to', config_path)
        return False


init_config('update', {'update': {'check_updates_online': True, 'ignored_update': 'v0.0'}})


for p in b9_paths:
    if isfile(p):
        b9_found = p
        break
else:
    b9_found = ''

for p in seeddb_paths:
    if isfile(p):
        seeddb_found = p
        break
else:
    seeddb_found = ''

# types
CCI = 'CTR Cart Image (".3ds", ".cci")'
CDN = 'CDN contents ("cetk", "tmd", and contents)'
CIA = 'CTR Importable Archive (".cia")'
EXEFS = 'Executable Filesystem (".exefs", "exefs.bin")'
NANDCTR = 'Nintendo 3DS NAND backup ("nand.bin")'
NANDTWL = 'Nintendo DSi NAND backup ("nand_dsi.bin")'
NANDHAC = 'Nintendo Switch NAND backup ("rawnand.bin")'
NCCH = 'NCCH (".cxi", ".cfa", ".ncch", ".app")'
ROMFS = 'Read-only Filesystem (".romfs", "romfs.bin")'
SD = 'SD Card Contents ("Nintendo 3DS" from SD)'
SRL = 'Nintendo DS ROM image (".nds", ".srl")'
THREEDSX = '3DSX Homebrew (".3dsx")'
TITLEDIR = 'Titles directory ("title" from NAND or SD)'

mount_types = {CCI: 'cci', CDN: 'cdn', CIA: 'cia', EXEFS: 'exefs', NANDCTR: 'nandctr', NANDHAC: 'nandhac',
               NANDTWL: 'nandtwl', NCCH: 'ncch', ROMFS: 'romfs', SD: 'sd', SRL: 'srl', THREEDSX: 'threedsx',
               TITLEDIR: 'titledir'}

mount_types_rv: 'Dict[str, str]' = {y: x for x, y in mount_types.items()}

ctr_types = (CCI, CDN, CIA, EXEFS, NANDCTR, NCCH, ROMFS, SD, THREEDSX, TITLEDIR)
twl_types = (NANDTWL, SRL)
hac_types = (NANDHAC,)
types_list = ctr_types + twl_types

types_requiring_b9 = {CCI, CDN, CIA, NANDCTR, NCCH, SD, TITLEDIR}

if windows:
    from ctypes import windll
    from platform import win32_ver
    from signal import CTRL_BREAK_EVENT
    from string import ascii_uppercase
    from subprocess import CREATE_NEW_PROCESS_GROUP
    from sys import stdout
    # noinspection PyUnresolvedReferences
    from winreg import OpenKey, QueryValueEx, HKEY_LOCAL_MACHINE

    from reg_shell import add_reg, del_reg, uac_enabled

    # unlikely, but this causes issues
    if stdout is None:  # happens if pythonw is used on windows
        # this one uses MessageBoxW directly because the gui hasn't been made yet.
        res = windll.user32.MessageBoxW(None, (
            'This is being run with the wrong Python executable.\n'
            'This should be installed as a module, then run using the py launcher on Python 3.6.1 or later.\n\n'
            'Click OK to open the ninfs repository on GitHub:\n'
            'https://github.com/ihaveamac/ninfs'),
                                        'ninfs', 0x00000010 | 0x00000001)
        if res == 1:
            webbrowser.open('https://github.com/ihaveamac/ninfs')
        exit(1)


    def get_unused_drives():
        # https://stackoverflow.com/questions/827371/is-there-a-way-to-list-all-the-available-drive-letters-in-python
        drives: List[str] = []
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in ascii_uppercase:
            if not bitmask & 1:
                drives.append(letter)
            bitmask >>= 1

        return drives


    def update_drives():
        o = get_unused_drives()
        app.changeOptionBox(MOUNTPOINT, (x + ':' for x in o))
        app.setOptionBox(MOUNTPOINT, o[-1] + ':')
elif macos:
    from platform import mac_ver

_used_pyinstaller = False
_ndw_resp = False
process: Popen = None
curr_mountpoint: str = None

pyver = f'{version_info[0]}.{version_info[1]}.{version_info[2]}'
if version_info[3] != 'final':
    pyver += f'{version_info[3][0]}{version_info[4]}'
pybits = 64 if maxsize > 0xFFFFFFFF else 32

app = gui('ninfs v' + version, showIcon=False, handleArgs=False)
if windows:
    app.setIcon(pjoin(dirname(__file__), 'data', 'windows.ico'))


def run_mount(module_type: str, item: str, mountpoint: str, extra_args: list = ()):
    global process, curr_mountpoint
    if process is None or process.poll() is not None:
        environ['BOOT9_PATH'] = b9_found
        environ['SEEDDB_PATH'] = seeddb_found
        args = [executable]
        if not _used_pyinstaller:
            args.append(dirname(__file__))
        args.extend((module_type, '-f', item, mountpoint))
        args.extend(extra_args)
        curr_mountpoint = mountpoint
        x, _ = get_terminal_size()
        print('-' * (x - 1))
        print('Running:', args)
        opts = {}
        if windows:
            opts['creationflags'] = CREATE_NEW_PROCESS_GROUP
        process = Popen(args, **opts)

        # check if the mount exists, or if the process exited before it
        check = isdir if windows else ismount
        while not check(mountpoint):
            sleep(1)
            if process.poll() is not None:
                show_mounterror()
                app.queueFunction(app.enableButton, MOUNT)
                return

        app.queueFunction(app.enableButton, UNMOUNT)

        if windows:
            with suppress(CalledProcessError):
                # not using startfile since i've been getting fatal errors (PyEval_RestoreThread) on windows
                #   for some reason
                # also this error always appears when calling explorer, so i'm ignoring it
                check_call(['explorer', mountpoint.replace('/', '\\')])
        elif macos:
            try:
                check_call(['/usr/bin/open', '-a', 'Finder', mountpoint])
            except CalledProcessError:
                print(f'Failed to open Finder on {mountpoint}')
                print_exc()
        else:  # probably linux
            try:
                check_call(['xdg-open', mountpoint])
            except CalledProcessError:
                print(f'Failed to open the file manager on {mountpoint}')
                print_exc()

        if process.wait() != 0:
            # just in case there are leftover mounts
            try:
                stop_mount()
            except CalledProcessError:
                print_exc()
            show_exiterror(process.returncode)

        app.queueFunction(app.disableButton, UNMOUNT)
        app.queueFunction(app.enableButton, MOUNT)


def stop_mount():
    if process is not None and process.poll() is None:
        print('Stopping')
        if windows:
            kill(process.pid, CTRL_BREAK_EVENT)
        else:
            # this is cheating...
            if macos:
                check_call(['diskutil', 'unmount', curr_mountpoint])
            else:
                # assuming linux or bsd, which have fusermount
                check_call(['fusermount', '-u', curr_mountpoint])


def press(button: str):
    if button == MOUNT:
        extra_args = []
        mount_type = app.getOptionBox('TYPE')
        app.disableButton(MOUNT)
        item = app.getEntry(mount_type + ITEM)
        if not item:
            show_noitemerror()
            app.enableButton(MOUNT)
            return

        if windows:
            if app.getRadioButton('mountpoint-choice') == 'Drive letter':
                if mount_type in {NANDCTR, NANDHAC, NANDTWL}:
                    res = app.okBox(
                        'ninfs Warning',
                        'You chose drive letter when using the NAND mount.\n'
                        '\n'
                        'Using a directory mount over a drive letter for NAND is highly '
                        'recommended because some tools like OSFMount will not be '
                        'able to read from files in a mount using a drive letter.\n'
                        '\n'
                        'Are you sure you want to continue?'
                    )
                    if not res:
                        app.enableButton(MOUNT)
                        return
                mountpoint = app.getOptionBox(MOUNTPOINT)
            else:
                mountpoint = app.getEntry(MOUNTPOINT)
                if not mountpoint:
                    show_nomperror()
                    app.enableButton(MOUNT)
                    return
                try:
                    # winfsp won't work on an existing directory
                    # so we try to use rmdir, which will delete it, only if it's empty
                    rmdir(mountpoint)
                except FileNotFoundError:
                    pass
                except Exception as e:
                    # noinspection PyUnresolvedReferences
                    if isinstance(e, OSError) and e.winerror == 145:  # "The directory is not empty"
                        show_mounterror_dir_win()
                    else:
                        print_exc()
                        show_mounterror()
                    app.enableButton(MOUNT)
                    return
        else:
            mountpoint = app.getEntry(MOUNTPOINT)
            if not mountpoint:
                show_nomperror()
                app.enableButton(MOUNT)
                return

        if mount_type == CDN:
            key = app.getEntry(CDN + 'key')
            if key:
                try:
                    _res = bytes.fromhex(key)
                except ValueError:
                    app.warningBox('ninfs Error', 'The given titlekey was not a valid hexstring.')
                    app.enableButton(MOUNT)
                    return
                if len(_res) != 16:
                    app.warningBox('ninfs Error', 'The given titlekey must be 32 characters.')
                    app.enableButton(MOUNT)
                    return
                extra_args.extend(('--dec-key', key))
        elif mount_type == NANDCTR:
            otp = app.getEntry(NANDCTR + 'otp')
            aw = app.getCheckBox(NANDCTR + 'aw')
            if otp:
                extra_args.extend(('--otp', otp))
            if not aw:
                extra_args.append('-r')
        elif mount_type == NANDHAC:
            try:
                int(item[-2:])
                # since int conversion succeded, assume this is a split file
                extra_args.append('--split-files')
            except ValueError:
                pass
            bis = app.getEntry(NANDHAC + 'bis')
            aw = app.getCheckBox(NANDHAC + 'aw')
            if not bis:
                app.warningBox('ninfs Error', 'BIS keys are required.')
                app.enableButton(MOUNT)
                return
            extra_args.extend(('--keys', bis))
            if not aw:
                extra_args.append('-r')
        elif mount_type == NANDTWL:
            consoleid = app.getEntry(NANDTWL + 'consoleid')
            aw = app.getCheckBox(NANDTWL + 'aw')
            if consoleid:
                if consoleid.lower().startswith('fw'):
                    app.warningBox('ninfs Error', 'A real Console ID does not start with FW. '
                                                     'It is a 16-character hexstring.')
                    app.enableButton(MOUNT)
                    return
                try:
                    _res = bytes.fromhex(consoleid)
                except ValueError:
                    app.warningBox('ninfs Error', 'The given Console ID was not a valid hexstring.')
                    app.enableButton(MOUNT)
                    return
                if len(_res) != 8:
                    app.warningBox('ninfs Error', 'The given Console ID must be 16 characters.')
                    app.enableButton(MOUNT)
                    return
                extra_args.extend(('--console-id', consoleid))
            if not aw:
                extra_args.append('-r')
        elif mount_type == SD:
            movable = app.getEntry(SD + 'movable')
            aw = app.getCheckBox(SD + 'aw')
            if not movable:
                app.warningBox('ninfs Error', 'A movable.sed is required.')
                app.enableButton(MOUNT)
                return
            extra_args.extend(('--movable', movable))
            if not aw:
                extra_args.append('-r')
        elif mount_type == TITLEDIR:
            decompress = app.getCheckBox(TITLEDIR + 'decompress')
            mount_all = app.getCheckBox(TITLEDIR + 'mountall')
            if decompress:
                extra_args.append('--decompress-code')
            if mount_all:
                extra_args.append('--mount-all')
        elif mount_type == EXEFS:
            decompress = app.getCheckBox(EXEFS + 'decompress')
            if decompress:
                extra_args.append('--decompress-code')

        if app.getCheckBox('debug'):
            extra_args.extend(('--do', app.getEntry('debug')))

        if not windows:
            allow_user = app.getRadioButton('allowuser')
            if allow_user == ALLOW_ROOT:
                extra_args.extend(('-o', 'allow_root'))
            elif allow_user == ALLOW_OTHER:
                extra_args.extend(('-o', 'allow_other'))

        if mount_type in types_requiring_b9:
            use_dev_keys = app.getCheckBox('devkeys')
            if use_dev_keys:
                extra_args.append('--dev')

        app.thread(run_mount, mount_types[mount_type], item, mountpoint, extra_args)

    elif button == UNMOUNT:
        app.disableButton(UNMOUNT)
        # noinspection PyBroadException
        try:
            stop_mount()
            app.enableButton(MOUNT)
        except Exception:
            print_exc()
            app.showSubWindow('unmounterror')
            app.enableButton(UNMOUNT)
    elif button == 'Settings & Help':
        show_extras()


def kill_process(_):
    process.kill()
    app.hideSubWindow('unmounterror')
    app.enableButton(MOUNT)
    app.disableButton(UNMOUNT)


current_type = 'default'


def check_mount_button(mount_type: str):
    if mount_type not in types_list:
        return
    if not b9_found and mount_type in types_requiring_b9:
        app.disableButton(MOUNT)
    else:
        if process is None or process.poll() is not None:
            app.enableButton(MOUNT)


def change_type(*_):
    global current_type
    mount_type: str = app.getOptionBox('TYPE')
    try:
        app.openLabelFrame('Mount settings')
    except ItemLookupError:
        app.setSticky(EASTWEST)
        app.startLabelFrame('Mount settings', row=1, colspan=3)
        app.setSticky(EASTWEST)
        app.showLabelFrame('Mount settings')

    app.hideFrame(current_type)

    try:
        app.showFrame(mount_type)
    except ItemLookupError:
        if mount_type == CCI:
            with app.frame(CCI, row=1, colspan=3):
                app.addLabel(CCI + LABEL1, FILE, row=0, column=0)
                app.addFileEntry(CCI + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(CCI + ITEM, DRAGFILE)

        elif mount_type == CDN:
            with app.frame(CDN, row=1, colspan=3):
                app.addLabel(CDN + LABEL1, DIRECTORY, row=0, column=0)
                app.addDirectoryEntry(CDN + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(CDN + ITEM, DRAGDIR)

                app.addLabel(CDN + LABEL2, 'Decrypted Titlekey*', row=3, column=0)
                app.addEntry(CDN + 'key', row=3, column=1, colspan=2)

                app.setEntryDefault(CDN + 'key', 'Insert a decrypted titlekey')
                app.addLabel(CDN + LABEL3, '*Not required if title has a cetk.', row=4, colspan=3)

        elif mount_type == CIA:
            with app.frame(CIA, row=1, colspan=3):
                app.addLabel(CIA + LABEL1, FILE, row=0, column=0)
                app.addFileEntry(CIA + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(CIA + ITEM, DRAGFILE)

        elif mount_type == EXEFS:
            with app.frame(EXEFS, row=1, colspan=3):
                app.addLabel(EXEFS + LABEL1, FILE, row=0, column=0)
                app.addFileEntry(EXEFS + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(EXEFS + ITEM, DRAGFILE)

                app.addLabel(EXEFS + LABEL3, 'Options', row=3, column=0)
                app.addNamedCheckBox('Decompress .code', EXEFS + 'decompress', row=3, column=1, colspan=1)

        elif mount_type == NANDCTR:
            with app.frame(NANDCTR, row=1, colspan=3):
                app.addLabel(NANDCTR + LABEL1, FILE, row=0, column=0)
                app.addFileEntry(NANDCTR + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(NANDCTR + ITEM, DRAGFILE)

                app.addLabel(NANDCTR + LABEL2, 'OTP file*', row=2, column=0)
                app.addFileEntry(NANDCTR + 'otp', row=2, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(NANDCTR + 'otp', DRAGFILE)

                app.addLabel(NANDCTR + 'label4', '*Not required if backup has essential.exefs from GodMode9.', row=3,
                             colspan=3)

                app.addLabel(NANDCTR + 'label5', 'Options', row=4, column=0)
                app.addNamedCheckBox('Allow writing', NANDCTR + 'aw', row=4, column=1, colspan=1)

                if has_dnd:
                    app.setEntryDropTarget(NANDCTR + 'otp', make_dnd_entry_check(NANDCTR + 'otp'))

        elif mount_type == NANDHAC:
            with app.frame(NANDHAC, row=1, colspan=3):
                app.addLabel(NANDHAC + LABEL1, FILE, row=0, column=0)
                app.addFileEntry(NANDHAC + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(NANDHAC + ITEM, DRAGFILE)

                app.addLabel(NANDHAC + LABEL2, 'BIS Keys', row=2, column=0)
                app.addFileEntry(NANDHAC + 'bis', row=2, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(NANDHAC + 'bis', DRAGFILE)

                app.addLabel(NANDCTR + LABEL3, 'Multi-part backups are supported (e.g. rawnand.bin.00)', row=3,
                             colspan=3)

                app.addLabel(NANDHAC + 'label4', 'Options', row=4, column=0)
                app.addNamedCheckBox('Allow writing', NANDHAC + 'aw', row=4, column=1, colspan=1)

                if has_dnd:
                    app.setEntryDropTarget(NANDHAC + 'bis', make_dnd_entry_check(NANDHAC + 'bis'))

        elif mount_type == NANDTWL:
            with app.frame(NANDTWL, row=1, colspan=3):
                app.addLabel(NANDTWL + LABEL1, FILE, row=0, column=0)
                app.addFileEntry(NANDTWL + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(NANDTWL + ITEM, DRAGFILE)

                app.addLabel(NANDTWL + LABEL2, 'Console ID*', row=2, column=0)
                app.addEntry(NANDTWL + 'consoleid', row=2, column=1, colspan=2)
                app.setEntryDefault(NANDTWL + 'consoleid', 'If required, input Console ID as hexstring')

                app.addLabel(NANDTWL + LABEL3, '*Not required if backup has nocash footer with ConsoleID/CID.', row=3,
                             colspan=3)

                app.addLabel(NANDTWL + 'label4', 'Options', row=5, column=0)
                app.addNamedCheckBox('Allow writing', NANDTWL + 'aw', row=5, column=1, colspan=1)

        elif mount_type == NCCH:
            with app.frame(NCCH, row=1, colspan=3):
                app.addLabel(NCCH + LABEL1, FILE, row=0, column=0)
                app.addFileEntry(NCCH + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(NCCH + ITEM, DRAGFILE)

        elif mount_type == ROMFS:
            with app.frame(ROMFS, row=1, colspan=3):
                app.addLabel(ROMFS + LABEL1, FILE, row=0, column=0)
                app.addFileEntry(ROMFS + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(ROMFS + ITEM, DRAGFILE)

        elif mount_type == SD:
            with app.frame(SD, row=1, colspan=3):
                app.addLabel(SD + LABEL1, DIRECTORY, row=0, column=0)
                app.addDirectoryEntry(SD + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(SD + ITEM, DRAGDIR)

                app.addLabel(SD + LABEL2, 'movable.sed', row=2, column=0)
                app.addFileEntry(SD + 'movable', row=2, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(SD + 'movable', DRAGFILE)

                app.addLabel(SD + LABEL3, 'Options', row=3, column=0)
                app.addNamedCheckBox('Allow writing', SD + 'aw', row=3, column=1, colspan=1)

                if has_dnd:
                    app.setEntryDropTarget(SD + 'movable', make_dnd_entry_check(SD + 'movable'))

        elif mount_type == THREEDSX:
            with app.frame(THREEDSX, row=1, colspan=3):
                app.addLabel(THREEDSX + LABEL1, FILE, row=0, column=0)
                app.addFileEntry(THREEDSX + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(THREEDSX + ITEM, DRAGFILE)

        elif mount_type == SRL:
            with app.frame(SRL, row=1, colspan=3):
                app.addLabel(SRL + LABEL1, FILE, row=0, column=0)
                app.addFileEntry(SRL + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(SRL + ITEM, DRAGFILE)

        elif mount_type == TITLEDIR:
            with app.frame(TITLEDIR, row=1, colspan=3):
                app.addLabel(TITLEDIR + LABEL1, DIRECTORY, row=0, column=0)
                app.addDirectoryEntry(TITLEDIR + ITEM, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                app.setEntryDefault(TITLEDIR + ITEM, DRAGFILE)

                app.addLabel(TITLEDIR + LABEL3, 'Options', row=3, column=0)
                app.addNamedCheckBox('Decompress .code (slow!)', TITLEDIR + 'decompress', row=3, column=1, colspan=1)
                app.addNamedCheckBox('Mount all contents', TITLEDIR + 'mountall', row=3, column=2, colspan=1)

        if has_dnd:
            app.setEntryDropTarget(mount_type + ITEM, make_dnd_entry_check(mount_type + ITEM))

    finally:
        app.stopLabelFrame()
        current_type = mount_type

        try:
            app.showLabelFrame('Mount point')
        except ItemLookupError:
            app.setSticky(EASTWEST)
            with app.labelFrame('Mount point', row=2, colspan=3):
                app.setSticky(EASTWEST)
                with app.frame('mountpoint-root', colspan=3):
                    if windows:
                        def rb_change(_):
                            if app.getRadioButton('mountpoint-choice') == 'Drive letter':
                                app.hideFrame('mountpoint-dir')
                                app.showFrame('mountpoint-drive')
                            else:
                                app.hideFrame('mountpoint-drive')
                                app.showFrame('mountpoint-dir')

                        app.addLabel('mountpoint-choice-label', 'Mount type', row=0)
                        app.addRadioButton('mountpoint-choice', 'Drive letter', row=0, column=1)
                        app.addRadioButton('mountpoint-choice', 'Directory', row=0, column=2)

                        app.setRadioButtonChangeFunction('mountpoint-choice', rb_change)
                        with app.frame('mountpoint-drive', row=1, colspan=3):
                            app.addLabel('mountlabel1', 'Drive letter', row=0, column=0)
                            # putting "WWWW" to avoid a warning
                            app.addOptionBox(MOUNTPOINT, ['WWWW'], row=0, column=1, colspan=2)

                        with app.frame('mountpoint-dir', row=1, colspan=3):
                            app.addLabel('mountlabel2', 'Mount point', row=0, column=0)
                            app.addDirectoryEntry(MOUNTPOINT, row=0, column=1, colspan=2).theButton.config(text=BROWSE)
                        app.hideFrame('mountpoint-dir')
                        # noinspection PyUnboundLocalVariable
                        update_drives()
                    else:
                        app.addLabel('mountlabel', 'Mount point', row=2, column=0)
                        app.addDirectoryEntry(MOUNTPOINT, row=2, column=1, colspan=2).theButton.config(text=BROWSE)
                    app.setEntryDefault(MOUNTPOINT, DRAGDIR)

                    def toggle_advanced_opts(_):
                        if app.getCheckBox('advopt'):
                            app.showLabelFrame('Advanced options')
                        else:
                            app.hideLabelFrame('Advanced options')

                    def choose_debug_location(_):
                        path: str = app.saveBox(fileName='ninfs.log', dirName=pjoin(home, 'Desktop'),
                                                fileTypes=(),
                                                fileExt='.log')
                        if path:
                            app.setEntry('debug', path)

                    app.addNamedCheckBox('Show advanced options', 'advopt', column=1, colspan=2)
                    app.setCheckBoxChangeFunction('advopt', toggle_advanced_opts)

                app.setSticky(EASTWEST)
                with app.labelFrame('Advanced options', colspan=3):
                    app.setSticky(EASTWEST)

                    app.addLabel('devkeys-label', 'Keys')
                    app.addNamedCheckBox('Use developer-unit keys', 'devkeys', row=PV, column=1, colspan=2)

                    if not windows:
                        app.addLabel('allowuser-label', 'External user access')
                        app.addRadioButton('allowuser', ALLOW_NONE, row=PV, column=1, colspan=2)
                        app.addRadioButton('allowuser', ALLOW_ROOT, column=1, colspan=2)
                        app.addRadioButton('allowuser', ALLOW_OTHER, column=1, colspan=2)
                        if not macos:
                            app.addMessage('allowuser-notice',
                                           'This may require extra permissions, such as adding the user to the '
                                           'fuse group, or editing /etc/fuse.conf.', column=1, colspan=2)
                            app.setMessageAlign('allowuser-notice', 'left')
                            app.setMessageAspect('allowuser-notice', 500)

                    app.addLabel('debug-label1', 'Debug output')
                    app.addNamedCheckBox('Enable debug output', 'debug', row=PV, column=1, colspan=2)
                    app.addLabel('debug-label2', 'Debug log file')
                    app.addNamedButton('Choose log location...', 'debug', choose_debug_location, row=PV, column=1,
                                       colspan=2)
                    app.addEntry('debug', column=1, colspan=2)
                    app.setEntryDefault('debug', 'Choose where to save above...')

                app.hideLabelFrame('Advanced options')

                app.addButtons([MOUNT, UNMOUNT], press, colspan=3)
                app.disableButton(UNMOUNT)

            if has_dnd:
                app.setEntryDropTarget(MOUNTPOINT, make_dnd_entry_check(MOUNTPOINT))

        check_mount_button(mount_type)

        try:
            if mount_type in types_requiring_b9:
                app.showFrame('FOOTER')
            else:
                app.hideFrame('FOOTER')
        except ItemLookupError:
            pass

        if mount_type in {NANDCTR, NANDHAC, NANDTWL} and windows:
            app.setRadioButton('mountpoint-choice', 'Directory')


def make_dnd_entry_check(entry_name: str):
    def handle(data: str):
        if data.startswith('{'):
            data = data[1:-1]
        app.setEntry(entry_name, data)

    return handle


print('Setting up GUI...')

with app.frame('loading', row=1, colspan=3):
    app.addLabel('l-label', 'Getting ready...', colspan=3)


def show_unknowntype(path: str):
    app.warningBox('ninfs Error',
                   "The type of the given file couldn't be detected."
                   "If you know it is a compatibile file, choose the "
                   "correct type and file an issue on GitHub if it works.\n\n"
                   + path)


def detect_type(fn: str):
    if fn.startswith('{'):
        fn = fn[1:-1]
    # noinspection PyBroadException
    try:
        with open(fn, 'rb') as f:
            mt = detect_format(f.read(0x400))
            if mt is not None:
                mount_type = mount_types_rv[mt]
            else:
                show_unknowntype(fn)
                return
    except (IsADirectoryError, PermissionError):  # PermissionError sometimes occurs on Windows
        if isfile(pjoin(fn, 'tmd')):
            mount_type = CDN
        else:
            try:
                next(iglob(pjoin(fn, '[0-9a-f]' * 32)))
            except StopIteration:
                # no entries
                mount_type = TITLEDIR
            else:
                # at least one entry
                mount_type = SD
    except Exception:
        print('Failed to get type of', fn)
        print_exc()
        return

    app.setOptionBox('TYPE', mount_type)
    app.setEntry(mount_type + ITEM, fn)
    app.showFrame(mount_type)


app.setSticky('new')
# this is here to force the width to be set
app.addOptionBox('TYPE', ('- Choose a type or drag a file/directory here -',), row=0, colspan=2)
app.setOptionBoxChangeFunction('TYPE', change_type)
app.addButton('Settings & Help', press, row=0, column=2)
try:
    app.setOptionBoxDropTarget('TYPE', detect_type)
    has_dnd = True
except Exception as e:
    print('Warning: Failed to enable Drag & Drop, will not be used.')
    print_exc()
    has_dnd = False

app.changeOptionBox('TYPE', (f'- Choose a type{" or drag a file/directory here" if has_dnd else ""} -',
                             '- Nintendo 3DS -', *ctr_types,
                             '- Nintendo DS / DSi -', *twl_types,
                             '- Nintendo Switch -', *hac_types),)

with app.frame('default', row=1, colspan=3):
    app.setSticky(EASTWEST)
    with app.labelFrame('Getting started', colspan=3):
        app.setSticky(EASTWEST)
        if has_dnd:
            app.addLabel('d-label1', 'To get started, drag the file to the box above.', colspan=2)
            app.addLabel('d-label2', 'You can also click it to manually choose a type.', colspan=2)
        else:
            app.addLabel('d-label1', 'To get started, choose a type to mount above.', colspan=2)
        app.addHorizontalSeparator(colspan=2)
        app.addLabel('d-label3', 'Need help?')
        app.addWebLink('View a tutorial here!', 'https://gbatemp.net/threads/499994/', column=1, row=PV)
        app.setLabelAlign('d-label3', 'right')
        app.setLinkAlign('View a tutorial here!', 'left')
app.hideFrame('default')  # to be shown later


def select_seeddb(sw):
    global seeddb_found
    path: str = app.openBox(title='Choose SeedDB', fileTypes=())
    if path:
        if getsize(path) % 0x10:
            app.warningBox('ninfs Error',
                           'The size for the selected SeedDB is not aligned to 0x10.')
            # shouldn't be calling this directly but i seem to have encounered a bug with parent=
            # noinspection PyProtectedMember
            app._bringToFront(sw)
            return
        with open(path, 'rb') as f:
            data = f.read(0x1FFFF0)
            target = pjoin(target_dir, 'seeddb.bin')
            makedirs(target_dir, exist_ok=True)
            with open(target, 'wb') as o:
                o.write(data)
            app.infoBox('ninfs', 'SeedDB was copied to:\n\n' + target)
            seeddb_found = target
            with suppress(ItemLookupError):
                app.hideLabel('no-seeddb')
                app.hideButton('fix-seeddb')
                if b9_found and seeddb_found:
                    app.hideFrame('FOOTER')
                app.hideSubWindow('no-seeddb')


if not b9_found or not seeddb_found:
    with app.frame('FOOTER', row=3, colspan=3):
        if not b9_found:
            app.addLabel('no-b9', 'boot9 was not found. Click for more details.', colspan=2)
            app.setLabelBg('no-b9', '#ff9999')
            app.addNamedButton('Fix boot9', 'fix-b9', lambda _: app.showSubWindow('no-b9'), row=PV, column=2)


            def select_b9(sw):
                global b9_found
                path: str = app.openBox(title='Choose boot9', fileTypes=(), parent='no-b9')
                if path:
                    if getsize(path) not in {0x8000, 0x10000}:
                        app.warningBox('ninfs Error',
                                       'The size for the selected boot9 match is not 0x8000 or 0x10000.')
                        # shouldn't be calling this directly but i seem to have encounered a bug with parent=
                        # noinspection PyProtectedMember
                        app._bringToFront(sw)
                        return
                    with open(path, 'rb') as f:
                        data = f.read(0x10000)
                        try:
                            fn = b9_hashes[sha256(data).hexdigest()]
                        except KeyError:
                            app.warningBox('ninfs Error', 'boot9 hash did not match. Please re-dump boot9.')
                            # noinspection PyProtectedMember
                            app._bringToFront(sw)
                            return
                        target = pjoin(target_dir, fn + '.bin')
                        makedirs(target_dir, exist_ok=True)
                        with open(target, 'wb') as o:
                            o.write(data)
                        app.infoBox('ninfs', 'boot9 was copied to:\n\n' + target)
                        b9_found = target
                        app.hideLabel('no-b9')
                        app.hideButton('fix-b9')
                        if b9_found and seeddb_found:
                            app.hideFrame('FOOTER')
                        check_mount_button(app.getOptionBox('TYPE'))
                        app.hideSubWindow('no-b9')


            with app.subWindow('no-b9', 'ninfs Error', modal=True) as sw:
                app.addLabel('boot9 was not found. It is needed for encryption.\n'
                             'Mount types that use encryption have been disabled.\n'
                             '\n'
                             'Choose this to automatically set up boot9.')
                app.addNamedButton('Select boot9 to copy...', 'no-b9-select', lambda _: select_b9(sw))
                app.setSticky(EASTWEST)
                app.addHorizontalSeparator()
                app.addLabel('The following paths were checked for a boot9 dump:')
                app.addListBox('b9-paths', b9_paths)
                app.setListBoxRows('b9-paths', len(b9_paths))
                app.setSticky('')
                app.addNamedButton(OK, 'no-b9-ok', lambda _: app.hideSubWindow('no-b9'))
                app.setResizable(False)

        if not seeddb_found:
            app.addLabel('no-seeddb', 'SeedDB was not found. Click for more details.', colspan=2)
            app.setLabelBg('no-seeddb', '#ffff99')
            app.addNamedButton('Fix SeedDB', 'fix-seeddb', lambda _: app.showSubWindow('no-seeddb'), row=PV,
                               column=2)

            with app.subWindow('no-seeddb', 'ninfs Error', modal=True) as sw:
                app.addLabel('SeedDB was not found. It is needed for encryption\n'
                             'of newer digital titles.\n'
                             '\n'
                             'Choose this to automatically set up SeedDB.')
                app.addNamedButton('Select SeedDB to copy...', 'no-seeddb-select', lambda _: select_seeddb(sw))
                app.setSticky(EASTWEST)
                app.addHorizontalSeparator()
                app.addLabel('The following paths were checked for SeedDB:')
                app.addListBox('seeddb-paths', seeddb_paths)
                app.setListBoxRows('seeddb-paths', len(seeddb_paths))
                app.setSticky('')
                app.addNamedButton(OK, 'no-seeddb-ok', lambda _: app.hideSubWindow('no-seeddb'))
                app.setResizable(False)
    app.hideFrame('FOOTER')

if windows:
    app.setFont(10)
elif macos:
    app.setFont(14)
app.setResizable(False)


# failed to mount subwindow
def show_mounterror():
    app.warningBox('ninfs Error', 'Failed to mount. Please check the output.')


# exited with error subwindow
def show_exiterror(errcode: int):
    app.warningBox('ninfs Error',
                   f'The mount process exited with an error code ({errcode}). Please check the output.')


# failed to mount to directory subwindow
if windows:
    def show_mounterror_dir_win():
        app.warningBox('ninfs Error',
                       'Failed to mount to the given mount point.\n'
                       'Please make sure the directory is empty or does not exist.')


def show_extras():
    try:
        app.showSubWindow('extras')
    except ItemLookupError:
        with app.subWindow('extras', 'ninfs Extras', modal=True, blocking=False) as sw:
            app.setSticky(EASTWEST)
            with app.labelFrame('Settings'):
                def checkbox_update(name: str):
                    if name == 'update-check':
                        option = app.getCheckBox('update-check')
                        if not write_config('update', 'update', 'check_updates_online', option):
                            app.errorBox('ninfs Error', 'Failed to write to config. Is the path read-only? '
                                                           'Check the output for more details.')

                app.addNamedCheckBox('Check for updates at launch', 'update-check')
                app.setCheckBox('update-check', update_config.getboolean('update', 'check_updates_online'))
                app.setCheckBoxChangeFunction('update-check', checkbox_update)

            app.setSticky(EASTWEST)
            with app.labelFrame('Update SeedDB', colspan=3):
                app.setSticky(EASTWEST)
                app.addLabel('updateseeddb-label', 'Update SeedDB to a newer database.', colspan=2)
                app.addNamedButton('Update', 'updateseeddb-btn', lambda _: select_seeddb(sw), row=PV, column=2)

            app.setSticky(EASTWEST)
            with app.labelFrame('Tutorial', colspan=3):
                app.setSticky(EASTWEST)
                app.addLabel('tutorial-label', 'View a tutorial on GBAtemp.', colspan=2)
                app.addNamedButton('Open', 'tutorial-btn',
                                   lambda _: webbrowser.open('https://gbatemp.net/threads/499994/'),
                                   row=PV, column=2)

            def _show_ctxmenu_window():
                app.showSubWindow('ctxmenu-window')
                app.hideSubWindow('extras')

            if windows:
                app.setSticky(EASTWEST)
                with app.labelFrame('Context Menu', colspan=3):
                    app.setSticky(EASTWEST)
                    app.addLabel('ctxmenu-label', 'Add an entry to the right-click menu.', colspan=2)
                    app.addNamedButton('Add', 'ctxmenu-btn', _show_ctxmenu_window, row=PV,
                                       column=2)

            def _show_about():
                app.showSubWindow('about')
                app.hideSubWindow('extras')

            app.setSticky(EASTWEST)
            with app.labelFrame('About', colspan=3):
                app.setSticky(EASTWEST)
                app.addLabel('about-label', 'Open the about dialog.')
                app.addNamedButton('Open', 'about-btn', _show_about, row=PV, column=2)

            app.setResizable(False)

        app.setSticky(EASTWEST)
        with app.subWindow('about', 'ninfs', modal=True, blocking=False):
            app.setSticky(EASTWEST)
            if windows:
                _ver = win32_ver()
                os_ver = 'Windows ' + _ver[0]
                if _ver[0] == '10':
                    k = OpenKey(HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows NT\CurrentVersion')
                    try:
                        r: str = QueryValueEx(k, 'ReleaseId')[0]
                    except FileNotFoundError:
                        r = '1507'  # assuming RTM, since this key only exists in 1511 and up
                    os_ver += ', version ' + r
                else:
                    if _ver[2] != 'SP0':
                        os_ver += ' ' + _ver[2]
            elif macos:
                os_ver = 'macOS ' + mac_ver()[0]
            else:
                os_ver = ''
            if os_ver:
                os_ver += '\n'
            app.addMessage('about-msg', f'ninfs v{version}\n'
                                        f'Running on Python {pyver} {pybits}-bit\n'
                                        f'{os_ver}'
                                        f'\n'
                                        f'ninfs is released under the MIT license.', colspan=4)
            app.setMessageAspect('about-msg', 500)
            app.addWebLink('View ninfs on GitHub', 'https://github.com/ihaveamac/ninfs', colspan=4)
            app.addLabel('These libraries are used in the project:', colspan=4)
            app.addWebLink('appJar', 'https://github.com/jarvisteach/appJar')
            app.addWebLink('PyCryptodome', 'https://github.com/Legrandin/pycryptodome', row=PV, column=1)
            app.addWebLink('fusepy', 'https://github.com/fusepy/fusepy', row=PV, column=2)
            app.addWebLink('PyInstaller', 'https://github.com/pyinstaller/pyinstaller', row=PV, column=3)
            app.setResizable(False)

        if windows:
            def add_entry(button: str):
                app.hideSubWindow('ctxmenu-window')
                if button == 'Add entry':
                    add_reg(_used_pyinstaller)
                elif button == 'Remove entry':
                    del_reg()

            with app.subWindow('ctxmenu-window', 'ninfs', modal=True):
                msg = (
                    'A new entry can be added to the Windows context menu when you right-click on a file, providing an '
                    'easy way to mount various files in Windows Explorer using ninfs.\n'
                    '\n'
                    'This will modify the registry to add it.')
                if _used_pyinstaller:
                    msg += ' If you move or rename the EXE, you will need to re-add the entry.'
                app.addMessage('extras-ctxmenu-label', msg)
                app.setMessageAspect('extras-ctxmenu-label', 300)
                app.addButtons(['Add entry', 'Remove entry', 'Cancel'], add_entry, colspan=3)
                app.setResizable(False)

        app.showSubWindow('extras')


# file/directory not set error
def show_noitemerror():
    app.infoBox('ninfs Error', 'Select a file or directory to mount.')


# mountpoint not set error
def show_nomperror():
    app.infoBox('ninfs Error', 'Select an empty directory to be the mount point.')


# failed to unmount subwindow
with app.subWindow('unmounterror', 'ninfs Error', modal=True, blocking=False):
    def unmount_ok(_):
        app.hideSubWindow('unmounterror')
        app.enableButton(UNMOUNT)


    app.addLabel('unmounterror-label', 'Failed to unmount. Please check the output.\n\n'
                                       'You can kill the process if it is not responding. '
                                       'This should be used as a last resort. '
                                       'The process should be unmounted normally.', colspan=2)
    app.addNamedButton(OK, 'unmounterror-ok', unmount_ok)
    app.addNamedButton('Kill process', 'unmounterror-kill', kill_process, row=PV, column=1)
    app.setResizable(False)


# maybe get the file via an argument to main? instead of taking it from argv
# it probably doesn't matter much
def main(_pyi=False, _allow_admin=False):
    global _used_pyinstaller
    _used_pyinstaller = _pyi
    print('Doing final setup...')
    try:
        # attempt importing all the fusepy stuff used in the mount scripts
        # if it fails, libfuse probably couldn't be found
        import fuse
    except EnvironmentError:
        # TODO: probably check if this was really "Unable to find libfuse" (this is aliased to OSError)
        if windows:
            res = app.yesNoBox('ninfs',
                               'Failed to import fusepy. WinFsp needs to be installed.\n\n'
                               'Would you like to open the WinFsp download page?\n'
                               'http://www.secfs.net/winfsp/download/')
            if res:
                webbrowser.open('http://www.secfs.net/winfsp/download/')
        elif macos:
            res = app.yesNoBox('ninfs',
                               'Failed to import fusepy. FUSE for macOS needs to be installed.\n\n'
                               'Would you like to open the FUSE for macOS download page?\n'
                               'https://osxfuse.github.io')
            if res:
                webbrowser.open('https://osxfuse.github.io')
        else:
            print("Failed to load fusepy. libfuse probably couldn't be found.")
        return 1

    if windows and not _allow_admin:
        isadmin: int = windll.shell32.IsUserAnAdmin()
        if isadmin and uac_enabled():
            app.warningBox('ninfs',
                           'This should not be run as administrator.\n'
                           'The mount point may not be accessible by your account normally, '
                           'only by the administrator.\n\n'
                           'If you are having issues with administrative tools not seeing files, '
                           'choose a directory as a mount point instead of a drive letter.')
            exit(1)

    def show_update(name: str, ver: str, info: str, url: str):
        def update_press(button: str):
            if button == 'Open release page':
                webbrowser.open(url)
                app.queueFunction(app.stop)
            elif button == 'Ignore this update':
                if not write_config('update', 'update', 'ignored_update', ver):
                    app.errorBox('ninfs Error', 'Failed to write to config. Is the path read-only? '
                                                   'Check the output for more details.')
            app.destroySubWindow('update')

        with app.subWindow('update', 'ninfs Update', modal=True):
            app.addLabel('update-label1', f'A new version of ninfs is available. You have v{version}.')
            app.addButtons(['Open release page', 'Ignore this update', 'Close'], update_press)
            with app.labelFrame(name):
                app.addMessage('update-info', info)
                app.setMessageAlign('update-info', 'left')
                app.setMessageAspect('update-info', 300)
            app.setResizable(False)

        app.showSubWindow('update')

    if update_config.getboolean('update', 'check_updates_online'):
        def update_check():
            # this will check for the latest non-prerelease, once there is one.
            # noinspection PyBroadException
            try:
                print(f'UPDATE: Checking for updates... (Currently running v{version})')
                ctx = SSLContext(PROTOCOL_TLSv1_2)
                release_url = 'https://api.github.com/repos/ihaveamac/ninfs/releases'
                current_ver: 'Version' = parse_version(version)
                if not current_ver.is_prerelease:
                    release_url += '/latest'
                with urlopen(release_url, context=ctx) as u:
                    u: HTTPResponse
                    res: List[Dict[str, Any]] = json.loads(u.read().decode('utf-8'))
                    latest_rel = res[0] if current_ver.is_prerelease else res
                    latest_ver: str = latest_rel['tag_name']
                    if parse_version(latest_ver) > current_ver:
                        name: str = latest_rel['name']
                        url: str = latest_rel['html_url']
                        info_all: str = latest_rel['body']
                        info = info_all[:info_all.find('------')].strip().replace('\r\n', '\n')

                        if latest_ver == update_config['update']['ignored_update']:
                            print(f'UPDATE: Update to {latest_ver} is available but ignored.')
                        else:
                            print(f'UPDATE: Update to {latest_ver} is available.')
                            app.queueFunction(show_update, name, latest_ver, info, url)
                    else:
                        print(f'UPDATE: No new version. (Latest is {latest_ver})')

            except Exception:
                print('UPDATE: Failed to check for update')
                print_exc()

        app.thread(update_check)
    else:
        print('UPDATE: Online update check disabled.')

    to_use = 'default'

    if len(argv) > 1:
        fn: str = abspath(argv[1])
        # noinspection PyBroadException
        try:
            with open(fn, 'rb') as f:
                mt = detect_format(f.read(0x400))
                if mt is not None:
                    mount_type = mount_types_rv[mt]
                    to_use = mount_type
                    file_to_use = fn
                else:
                    show_unknowntype(fn)
        except (IsADirectoryError, PermissionError):  # PermissionError sometimes occurs on Windows
            if isfile(pjoin(fn, 'tmd')):
                mount_type = CDN
            else:
                try:
                    next(iglob(pjoin(fn, '[0-9a-f]' * 32)))
                except StopIteration:
                    # no entries
                    mount_type = TITLEDIR
                else:
                    # at least one entry
                    mount_type = SD
            to_use = mount_type
            file_to_use = fn
        except Exception:
            print('Failed to get type of', fn)
            print_exc()

    # kinda lame way to prevent a resize bug
    def sh():
        if to_use == 'default':
            app.queueFunction(app.showFrame, 'default')
        else:
            app.queueFunction(detect_type, file_to_use)
        app.queueFunction(app.hideFrame, 'loading')

    app.thread(sh)

    print('Starting the GUI!')
    app.go()
    stop_mount()
    return 0
