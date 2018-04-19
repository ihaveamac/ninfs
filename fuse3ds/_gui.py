# not very good with gui development...
# don't read this file, it sucks

# TODO: remove this when 3.5 support is removed
from sys import hexversion, exit
if hexversion < 0x030601F0:  # disable for 3.5
    exit('GUI is not available before Python 3.6.1.')

import json
import subprocess
import webbrowser
from contextlib import suppress
from glob import iglob
from os import environ, kill, rmdir
from os.path import abspath, isfile, isdir, ismount, dirname, join as pjoin
from shutil import get_terminal_size
from ssl import PROTOCOL_TLSv1_2, SSLContext
from sys import argv, executable, platform, version_info, maxsize
from time import sleep
from traceback import print_exc
from typing import TYPE_CHECKING
from urllib.request import urlopen

from appJar import gui
from pkg_resources import parse_version

from __init__ import __version__ as version
from fmt_detect import detect_format
from pyctr.util import config_dirs

if TYPE_CHECKING:
    from http.client import HTTPResponse as HTTPResp
    from typing import Any, Dict, List

MOUNT = 'Mount'
UNMOUNT = 'Unmount'
DIRECTORY = 'Directory'
FILE = 'File'
ITEM = 'item'
EASTWEST = 'ew'
OK = 'OK'

b9_paths = [pjoin(config_dirs[0] + '/boot9.bin'), pjoin(config_dirs[0] + '/boot9_prot.bin'),
            pjoin(config_dirs[1] + '/boot9.bin'), pjoin(config_dirs[1] + '/boot9_prot.bin')]
with suppress(KeyError):
    b9_paths.insert(0, environ['BOOT9_PATH'])

seeddb_paths = [pjoin(config_dirs[0] + '/seeddb.bin'), pjoin(config_dirs[1] + '/seeddb.bin')]
with suppress(KeyError):
    seeddb_paths.insert(0, environ['SEEDDB_PATH'])

for p in b9_paths:
    if isfile(p):
        b9_found = True
        break
else:
    b9_found = False

for p in seeddb_paths:
    if isfile(p):
        seeddb_found = True
        break
else:
    seeddb_found = False

# types
CCI = 'CTR Cart Image (".3ds", ".cci")'
CDN = 'CDN contents ("cetk", "tmd", and contents)'
CIA = 'CTR Importable Archive (".cia")'
EXEFS = 'Executable Filesystem (".exefs", "exefs.bin")'
NAND = 'NAND backup ("nand.bin")'
NCCH = 'NCCH (".cxi", ".cfa", ".ncch", ".app")'
ROMFS = 'Read-only Filesystem (".romfs", "romfs.bin")'
SD = 'SD Card Contents ("Nintendo 3DS" from SD)'
THREEDSX = '3DSX Homebrew (".3dsx")'
TITLEDIR = 'Titles directory ("title" from NAND or SD)'

mount_types = {CCI: 'cci', CDN: 'cdn', CIA: 'cia', EXEFS: 'exefs', NAND: 'nand', NCCH: 'ncch', ROMFS: 'romfs', SD: 'sd',
               THREEDSX: 'threedsx', TITLEDIR: 'titledir'}

mount_types_rv = {y: x for x, y in mount_types.items()}  # type: Dict[str, str]

types_list = (CCI, CDN, CIA, EXEFS, NAND, NCCH, ROMFS, SD, THREEDSX, TITLEDIR)

windows = platform == 'win32'  # only for native windows, not cygwin
macos = platform == 'darwin'

if windows:
    from ctypes import windll
    from signal import CTRL_BREAK_EVENT
    from string import ascii_uppercase
    from sys import stdout

    from reg_shell import add_reg, del_reg

    # unlikely, but this causes issues
    if stdout is None:  # happens if pythonw is used on windows
        res = windll.user32.MessageBoxW(None, (
            'This is being run with the wrong Python executable.\n'
            'This should be installed as a module, then run using the py launcher on Python 3.5.2 or later.\n\n'
            'Click OK to open the fuse-3ds repository on GitHub:\n'
            'https://github.com/ihaveamac/fuse-3ds'),
                                        'fuse-3ds', 0x00000010 | 0x00000001)
        if res == 1:
            webbrowser.open('https://github.com/ihaveamac/fuse-3ds')
        exit(1)

    # https://stackoverflow.com/questions/827371/is-there-a-way-to-list-all-the-available-drive-letters-in-python
    def get_unused_drives():
        drives = []
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in ascii_uppercase:
            if not bitmask & 1:
                drives.append(letter)
            bitmask >>= 1

        return drives

    def update_drives():
        app.changeOptionBox('mountpoint', (x + ':' for x in get_unused_drives()))

_used_pyinstaller = False
process = None  # type: subprocess.Popen
curr_mountpoint = None  # type: str

app = gui('fuse-3ds v' + version, showIcon=False, handleArgs=False)


def run_mount(module_type: str, item: str, mountpoint: str, extra_args: list = ()):
    global process, curr_mountpoint
    if process is None or process.poll() is not None:
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
            # noinspection PyUnresolvedReferences
            opts['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(args, **opts)

        # check if the mount exists, or if the process exited before it
        check = isdir if windows else ismount
        while not check(mountpoint):
            sleep(1)
            if process.poll() is not None:
                app.queueFunction(app.showSubWindow, 'mounterror')
                app.queueFunction(app.enableButton, MOUNT)
                return

        app.queueFunction(app.enableButton, UNMOUNT)

        if windows:
            with suppress(subprocess.CalledProcessError):
                # not using startfile since i've been getting fatal errors (PyEval_RestoreThread) on windows
                #   for some reason
                # also this error always appears when calling explorer, so i'm ignoring it
                subprocess.check_call(['explorer', mountpoint.replace('/', '\\')])
        elif macos:
            try:
                subprocess.check_call(['/usr/bin/open', '-a', 'Finder', mountpoint])
            except subprocess.CalledProcessError:
                print('Failed to open Finder on {}'.format(mountpoint))
                print_exc()

        if process.wait() != 0:
            # just in case there are leftover mounts
            try:
                stop_mount()
            except subprocess.CalledProcessError:
                print_exc()
            app.queueFunction(app.setLabel, 'exiterror-label',
                              'The mount process exited with an error code ({}). '
                              'Please check the output.'.format(process.returncode))
            app.queueFunction(app.showSubWindow, 'exiterror')

        app.queueFunction(app.disableButton, UNMOUNT)
        app.queueFunction(app.enableButton, MOUNT)


def stop_mount():
    global process
    if process is not None and process.poll() is None:
        print('Stopping')
        if windows:
            kill(process.pid, CTRL_BREAK_EVENT)
        else:
            # this is cheating...
            if platform == 'darwin':
                subprocess.check_call(['diskutil', 'unmount', curr_mountpoint])
            else:
                # assuming linux or bsd, which have fusermount
                subprocess.check_call(['fusermount', '-u', curr_mountpoint])


def press(button: str):
    if button == MOUNT:
        extra_args = []
        mount_type = app.getOptionBox('TYPE')
        app.disableButton(MOUNT)
        item = app.getEntry(mount_type + ITEM)
        if not item:
            app.showSubWindow('noitemerror')
            app.enableButton(MOUNT)
            return

        if windows:
            if app.getRadioButton('mountpoint-choice') == 'Drive letter':
                mountpoint = app.getOptionBox('mountpoint')
            else:
                mountpoint = app.getEntry('mountpoint')
                try:
                    # winfsp won't work on an existing directory
                    # so we try to use rmdir, which will delete it, only if it's empty
                    rmdir(mountpoint)
                except FileNotFoundError:
                    pass
                except Exception as e:
                    # noinspection PyUnresolvedReferences
                    if isinstance(e, OSError) and e.winerror == 145:  # "The directory is not empty"
                        app.showSubWindow('mounterror-dir-win')
                    else:
                        print_exc()
                        app.showSubWindow('mounterror')
                    app.enableButton(MOUNT)
                    return
        else:
            mountpoint = app.getEntry('mountpoint')
            if not mountpoint:
                app.showSubWindow('nomperror')
                app.enableButton(MOUNT)
                return

        if mount_type == CDN:
            key = app.getEntry(CDN + 'key')
            if key:
                extra_args.extend(('--dec-key', key))
        elif mount_type == NAND:
            otp = app.getEntry(NAND + 'otp')
            cid = app.getEntry(NAND + 'cid')
            aw = app.getCheckBox(NAND + 'aw')
            if otp:
                extra_args.extend(('--otp', otp))
            if cid:
                extra_args.extend(('--cid', cid))
            if not aw:
                extra_args.append('-r')
        elif mount_type == SD:
            movable = app.getEntry(SD + 'movable')
            aw = app.getCheckBox(SD + 'aw')
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
    elif button == 'Help & Extras':
        app.showSubWindow('extras')


def kill_process(_):
    process.kill()
    app.hideSubWindow('unmounterror')
    app.enableButton(MOUNT)
    app.disableButton(UNMOUNT)


def change_type(*_):
    mount_type = app.getOptionBox('TYPE')
    app.hideFrame('default')
    app.showLabelFrame('Mount point')
    app.showLabelFrame('Mount settings')
    for t in mount_types:
        if t == mount_type:
            app.showFrame(t)
        else:
            app.hideFrame(t)
    if not b9_found and mount_type in {CCI, CDN, CIA, NAND, NCCH, SD, TITLEDIR}:
        app.disableButton(MOUNT)
    else:
        if process is None or process.poll() is not None:
            app.enableButton(MOUNT)


def make_dnd_entry_check(entry_name: str):
    def handle(data: str):
        if data.startswith('{'):
            data = data[1:-1]
        app.setEntry(entry_name, data)

    return handle


with app.frame('loading', row=1, colspan=3):
    app.addLabel('l-label', 'Getting ready...', colspan=3)

app.setSticky(EASTWEST)
with app.labelFrame('Mount settings', row=1, colspan=3):
    app.setSticky(EASTWEST)
    with app.frame(CCI, row=1, colspan=3):
        app.addLabel(CCI + 'label1', FILE, row=0, column=0)
        app.addFileEntry(CCI + ITEM, row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(CCI + ITEM, 'Drag a file here or browse...')
    app.hideFrame(CCI)

    with app.frame(CDN, row=1, colspan=3):
        app.addLabel(CDN + 'label1', DIRECTORY, row=0, column=0)
        app.addDirectoryEntry(CDN + ITEM, row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(CDN + ITEM, 'Drag a directory here or browse...')
        app.addLabel(CDN + 'label2', 'Decrypted Titlekey*', row=3, column=0)
        app.addEntry(CDN + 'key', row=3, column=1, colspan=2)
        app.setEntryDefault(CDN + 'key', 'Insert a decrypted titlekey')
        app.addLabel(CDN + 'label3', '*Not required if title has a cetk.', row=4, colspan=3)
    app.hideFrame(CDN)

    with app.frame(CIA, row=1, colspan=3):
        app.addLabel(CIA + 'label1', FILE, row=0, column=0)
        app.addFileEntry(CIA + ITEM, row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(CIA + ITEM, 'Drag a file here or browse...')
    app.hideFrame(CIA)

    with app.frame(EXEFS, row=1, colspan=3):
        app.addLabel(EXEFS + 'label1', FILE, row=0, column=0)
        app.addFileEntry(EXEFS + ITEM, row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(EXEFS + ITEM, 'Drag a file here or browse...')
    app.hideFrame(EXEFS)

    with app.frame(NAND, row=1, colspan=3):
        app.addLabel(NAND + 'label1', FILE, row=0, column=0)
        app.addFileEntry(NAND + ITEM, row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(NAND + ITEM, 'Drag a file here or browse...')
        app.addLabel(NAND + 'label2', 'OTP file*', row=2, column=0)
        app.addFileEntry(NAND + 'otp', row=2, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(NAND + 'otp', 'Drag a file here or browse...')
        app.addLabel(NAND + 'label3', 'CID file*', row=3, column=0)
        app.addFileEntry(NAND + 'cid', row=3, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(NAND + 'cid', 'Drag a file here or browse...')
        app.addLabel(NAND + 'label4', '*Not required if backup has essential.exefs from GodMode9.', row=4, colspan=3)
        app.addLabel(NAND + 'label5', 'Options', row=5, column=0)
        app.addNamedCheckBox('Allow writing', NAND + 'aw', row=5, column=1, colspan=1)
    app.hideFrame(NAND)

    with app.frame(NCCH, row=1, colspan=3):
        app.addLabel(NCCH + 'label1', FILE, row=0, column=0)
        app.addFileEntry(NCCH + ITEM, row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(NCCH + ITEM, 'Drag a file here or browse...')
    app.hideFrame(NCCH)

    with app.frame(ROMFS, row=1, colspan=3):
        app.addLabel(ROMFS + 'label1', FILE, row=0, column=0)
        app.addFileEntry(ROMFS + ITEM, row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(ROMFS + ITEM, 'Drag a file here or browse...')
    app.hideFrame(ROMFS)

    with app.frame(SD, row=1, colspan=3):
        app.addLabel(SD + 'label1', DIRECTORY, row=0, column=0)
        app.addDirectoryEntry(SD + ITEM, row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(SD + ITEM, 'Drag a directory here or browse...')
        app.addLabel(SD + 'label2', 'movable.sed', row=2, column=0)
        app.addFileEntry(SD + 'movable', row=2, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(SD + 'movable', 'Drag a file here or browse...')
        app.addLabel(SD + 'label3', 'Options', row=3, column=0)
        app.addNamedCheckBox('Allow writing', SD + 'aw', row=3, column=1, colspan=1)
    app.hideFrame(SD)

    with app.frame(THREEDSX, row=1, colspan=3):
        app.addLabel(THREEDSX + 'label1', FILE, row=0, column=0)
        app.addFileEntry(THREEDSX + ITEM, row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(THREEDSX + ITEM, 'Drag a file here or browse...')
    app.hideFrame(THREEDSX)

    with app.frame(TITLEDIR, row=1, colspan=3):
        app.addLabel(TITLEDIR + 'label1', DIRECTORY, row=0, column=0)
        app.addDirectoryEntry(TITLEDIR + ITEM, row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.setEntryDefault(TITLEDIR + ITEM, 'Drag a file here or browse...')
        app.addLabel(TITLEDIR + 'label3', 'Options', row=3, column=0)
        app.addNamedCheckBox('Decompress .code (slow!)', TITLEDIR + 'decompress', row=3, column=1, colspan=1)
        app.addNamedCheckBox('Mount all contents', TITLEDIR + 'mountall', row=3, column=2, colspan=1)
    app.hideFrame(TITLEDIR)

with app.subWindow('unknowntype', 'fuse-3ds Error', modal=True):
    app.addLabel('unknowntype-label1', "The type of the given file couldn't be detected.\n"
                                       "If you know it is a compatibile file, choose the \n"
                                       "correct type and file an issue on GitHub if it works.")
    app.addLabel('unknowntype-label2', '<filepath>')
    app.addNamedButton(OK, 'unknowntype-ok', lambda _: app.hideSubWindow('unknowntype'))
    app.setResizable(False)


def detect_type(fn: str):
    if fn.startswith('{'):
        fn = fn[1:-1]
    # noinspection PyBroadException
    try:
        with open(fn, 'rb') as f:
            mt = detect_format(f.read(0x200))
            if mt is not None:
                mount_type = mount_types_rv[mt]
            else:
                app.setLabel('unknowntype-label2', fn)
                app.showSubWindow('unknowntype')
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


app.setSticky(EASTWEST)
with app.labelFrame('Mount point', row=2, colspan=3):
    app.setSticky(EASTWEST)
    if windows:
        def rb_change(_):
            if app.getRadioButton('mountpoint-choice') == 'Drive letter':
                app.hideFrame('mountpoint-dir')
                app.showFrame('mountpoint-drive')
            else:
                app.hideFrame('mountpoint-drive')
                app.showFrame('mountpoint-dir')

        app.addLabel('mountpoint-choice-label', 'Mount type', row=0)
        app.addRadioButton('mountpoint-choice', "Drive letter", row=0, column=1)
        app.addRadioButton('mountpoint-choice', "Directory", row=0, column=2)
        app.setRadioButtonChangeFunction('mountpoint-choice', rb_change)
        with app.frame('mountpoint-drive', row=1, colspan=3):
            app.addLabel('mountlabel1', 'Drive letter', row=0, column=0)
            app.addOptionBox('mountpoint', ['WWWW'], row=0, column=1, colspan=2)  # putting "WWWW" to avoid a warning
        with app.frame('mountpoint-dir', row=1, colspan=3):
            app.addLabel('mountlabel2', 'Mount point', row=0, column=0)
            app.addDirectoryEntry('mountpoint', row=0, column=1, colspan=2).theButton.config(text='Browse...')
        app.hideFrame('mountpoint-dir')
        # noinspection PyUnboundLocalVariable
        update_drives()
    else:
        app.addLabel('mountlabel', 'Mount point', row=2, column=0)
        app.addDirectoryEntry('mountpoint', row=2, column=1, colspan=2).theButton.config(text='Browse...')
    app.setEntryDefault('mountpoint', 'Drag a directory here or browse...')

    app.addButtons([MOUNT, UNMOUNT], press, colspan=3)
    app.disableButton(UNMOUNT)
app.hideLabelFrame('Mount point')

# noinspection PyBroadException
try:
    for t in types_list:
        app.setEntryDropTarget(t + ITEM, make_dnd_entry_check(t + ITEM))
    app.setEntryDropTarget(NAND + 'otp', make_dnd_entry_check(NAND + 'otp'))
    app.setEntryDropTarget(NAND + 'cid', make_dnd_entry_check(NAND + 'cid'))
    app.setEntryDropTarget(SD + 'movable', make_dnd_entry_check(SD + 'movable'))
    app.setEntryDropTarget('mountpoint', make_dnd_entry_check('mountpoint'))
    has_dnd = True
except Exception as e:
    print('Warning: Failed to enable Drag & Drop, will not be used.')
    print_exc()
    has_dnd = False

app.setSticky('new')
app.addOptionBox('TYPE', ('- Choose a type{} -'.format(' or drag a file/directory here' if has_dnd else ''),
                          *types_list), row=0, colspan=2)
app.setOptionBoxChangeFunction('TYPE', change_type)
app.addButton('Help & Extras', press, row=0, column=2)
if has_dnd:
    app.setOptionBoxDropTarget('TYPE', detect_type)

with app.frame('default', row=1, colspan=3):
    app.setSticky(EASTWEST)
    with app.labelFrame('Getting started', colspan=3):
        app.setSticky(EASTWEST)
        if has_dnd:
            app.addLabel('d-label1', 'To get started, drag the file to the box above.', colspan=3)
            app.addLabel('d-label2', 'You can also click it to manually choose a type.', colspan=3)
        else:
            app.addLabel('d-label1', 'To get started, choose a type to mount above.', colspan=3)
        app.addLabel('d-label3', 'If you need help, click "Help" at the top-right.', colspan=3)
app.hideFrame('default')  # to be shown later

if not b9_found or not seeddb_found:
    with app.frame('FOOTER', row=3, colspan=3):
        if not b9_found:
            app.addLabel('no-b9', 'boot9 was not found. Click for more details.', colspan=2)
            app.setLabelBg('no-b9', '#ff9999')
            app.addNamedButton('Fix boot9 (NYI)', 'fix-b9', lambda: None, row='previous', column=2)
            app.disableButton(MOUNT)

        if not seeddb_found:
            app.addLabel('no-seeddb', 'SeedDB was not found. Click for more details.', colspan=2)
            app.setLabelBg('no-seeddb', '#ffff99')
            app.addNamedButton('Fix SeedDB (NYI)', 'fix-seeddb', lambda: None, row='previous', column=2)

if windows:
    app.setFont(10)
elif macos:
    app.setFont(14)
app.setResizable(False)

# failed to mount subwindow
with app.subWindow('mounterror', 'fuse-3ds Error', modal=True, blocking=True):
    app.addLabel('mounterror-label', 'Failed to mount. Please check the output.')
    app.addNamedButton(OK, 'mounterror-ok', lambda _: app.hideSubWindow('mounterror'))
    app.setResizable(False)

# exited with error subwindow
with app.subWindow('exiterror', 'fuse-3ds Error', modal=True, blocking=True):
    app.addLabel('exiterror-label', 'The mount process exited with an error code (<errcode>). Please check the output.')
    app.addNamedButton(OK, 'exiterror-ok', lambda _: app.hideSubWindow('exiterror'))
    app.setResizable(False)

if windows:
    # failed to mount to directory subwindow
    with app.subWindow('mounterror-dir-win', 'fuse-3ds Error', modal=True, blocking=True):
        app.addLabel('mounterror-dir-label', 'Failed to mount to the given mount point.\n'
                                             'Please make sure the directory is empty or does not exist.')
        app.addNamedButton(OK, 'mounterror-dir-ok', lambda _: app.hideSubWindow('mounterror-dir-win'))
        app.setResizable(False)

with app.subWindow('extras', 'fuse-3ds Extras', modal=True, blocking=True):
    app.setSticky(EASTWEST)
    with app.labelFrame('Tutorial', colspan=3):
        app.setSticky(EASTWEST)
        app.addLabel('tutorial-label', 'View a tutorial on GBAtemp.', colspan=2)
        app.addNamedButton('Open', 'tutorial-btn', lambda _: webbrowser.open('https://gbatemp.net/threads/499994/'),
                           row='previous', column=2)

    app.setSticky(EASTWEST)
    with app.labelFrame('GitHub Repository', colspan=3):
        app.setSticky(EASTWEST)
        app.addLabel('repo-label', 'View the repository on GitHub.')
        app.addNamedButton('Open', 'repo-btn', lambda _: webbrowser.open('https://github.com/ihaveamac/fuse-3ds'),
                           row='previous', column=2)

    if windows:
        app.setSticky(EASTWEST)
        with app.labelFrame('Context Menu', colspan=3):
            app.setSticky(EASTWEST)
            app.addLabel('ctxmenu-label', 'Add an entry to the right-click menu.', colspan=2)
            app.addNamedButton('Add', 'ctxmenu-btn', lambda _: app.showSubWindow('ctxmenu-window'),
                               row='previous', column=2)

    with app.frame('extras-footer', colspan=3):
        app.addHorizontalSeparator()
        app.addLabel('footer', 'fuse-3ds v{0} running on Python {1[0]}.{1[1]}.{1[2]} {2}-bit on {3}'.format(
            version, version_info, '64' if maxsize > 0xFFFFFFFF else '32', platform))

    app.setResizable(False)

# file/directory not set error
with app.subWindow('noitemerror', 'fuse-3ds Error', modal=True, blocking=True):
    app.addLabel('Select a file or directory to mount.')
    app.addNamedButton(OK, 'noitemerror-ok', lambda _: app.hideSubWindow('noitemerror'))

# mountpoint not set error
with app.subWindow('nomperror', 'fuse-3ds Error', modal=True, blocking=True):
    app.addLabel('Select an empty directory to be the mount point.')
    app.addNamedButton(OK, 'nomperror-ok', lambda _: app.hideSubWindow('nomperror'))

# failed to unmount subwindow
with app.subWindow('unmounterror', 'fuse-3ds Error', modal=True, blocking=True):
    def unmount_ok(_):
        app.hideSubWindow('unmounterror')
        app.enableButton(UNMOUNT)

    app.addLabel('unmounterror-label', 'Failed to unmount. Please check the output.\n\n'
                                       'You can kill the process if it is not responding.\n'
                                       'This should be used as a last resort.'
                                       'The process should be unmounted normally.', colspan=2)
    app.addNamedButton(OK, 'unmounterror-ok', unmount_ok)
    app.addNamedButton('Kill process', 'unmounterror-kill', kill_process, row='previous', column=1)
    app.setResizable(False)


# maybe get the file via an argument to main? instead of taking it from argv
# it probably doesn't matter much
def main(_pyi=False, _allow_admin=False):
    global _used_pyinstaller
    _used_pyinstaller = _pyi
    try:
        # attempt importing all the fusepy stuff used in the mount scripts
        # if it fails, libfuse probably couldn't be found
        from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
    except EnvironmentError:
        # TODO: probably check if this was really "Unable to find libfuse" (this is aliased to OSError)
        if windows:
            if _used_pyinstaller:  # the right fusepy has to be included if it's a pyinstaller exe
                res = windll.user32.MessageBoxW(None, (
                    'Failed to import fusepy. WinFsp needs to be installed.\n\n'
                    'Click OK to open the WinFsp download page:\n'
                    'http://www.secfs.net/winfsp/download/'),
                                                'fuse-3ds', 0x00000010 | 0x00000001)
                if res == 1:
                    webbrowser.open('http://www.secfs.net/winfsp/download/')
            else:
                res = windll.user32.MessageBoxW(None, (
                    'Failed to import fusepy. Either WinFsp or fusepy needs to be installed.\n'
                    'Please check the README of fuse-3ds for more details.\n\n'
                    'Click OK to open the fuse-3ds repository on GitHub:\n'
                    'https://github.com/ihaveamac/fuse-3ds'),
                                                'fuse-3ds', 0x00000010 | 0x00000001)
                if res == 1:
                    webbrowser.open('https://github.com/ihaveamac/fuse-3ds')
        elif macos:
            print('Failed to load fusepy. Make sure FUSE for macOS (osxfuse) is installed.\n'
                  '  https://osxfuse.github.io')
        else:
            print("Failed to load fusepy. libfuse probably couldn't be found.")
        return 1

    if windows and not _allow_admin:
        if windll.shell32.IsUserAnAdmin():
            windll.user32.MessageBoxW(None, (
                'This should not be run as administrator.\n'
                'The mount point may not be accessible by your account normally, '
                'only by the administrator.\n\n'
                'If you are having issues with administrative tools not seeing files, '
                'choose a directory as a mount point instead of a drive letter.'),
                                      'fuse-3ds', 0x00000010)
            exit(1)

    # this will check for the latest non-prerelease, once there is one.
    # noinspection PyBroadException
    try:
        print('Checking for updates... (Currently running v{})'.format(version))
        ctx = SSLContext(PROTOCOL_TLSv1_2)
        with urlopen('https://api.github.com/repos/ihaveamac/fuse-3ds/releases', context=ctx) as u:  # type: HTTPResp
            res = json.loads(u.read().decode('utf-8'))  # type: List[Dict[str, Any]]
            latest_ver = res[0]['tag_name']  # type: str
            if parse_version(latest_ver) > parse_version(version):
                name = res[0]['name']  # type: str
                url = res[0]['html_url']  # type: str
                info_all = res[0]['body']  # type: str
                info = info_all[:info_all.find('------')].strip().replace('\r\n', '\n')

                def update_press(button: str):
                    if button == 'Open release page':
                        webbrowser.open(url)
                        app.queueFunction(app.stop)
                    app.destroySubWindow('update')

                with app.subWindow('update', 'fuse-3ds Update', modal=True, blocking=True):
                    app.addLabel('update-label1', 'A new version of fuse-3ds is available. '
                                                  'You have v{}.'.format(version))
                    app.addButtons(['Open release page', 'Close'], update_press)
                    with app.labelFrame(name):
                        app.addMessage('update-info', info)
                        app.setMessageAlign('update-info', 'left')
                    app.setResizable(False)

                app.queueFunction(app.showSubWindow, 'update')
            else:
                print('No new version. (Latest is {})'.format(latest_ver))

    except Exception:
        print('Failed to check for update')
        print_exc()

    to_use = 'default'

    if len(argv) > 1:
        fn = abspath(argv[1])  # type: str
        try:
            with open(fn, 'rb') as f:
                mt = detect_format(f.read(0x200))
                if mt is not None:
                    mount_type = mount_types_rv[mt]
                    to_use = mount_type
                    app.setEntry(mount_type + ITEM, fn)
                else:
                    app.setLabel('unknowntype-label2', fn)
                    app.queueFunction(app.showSubWindow, 'unknowntype')
        except Exception as e:
            print('Failed to get type of {}: {}: {}'.format(fn, type(e).__name__, e))

    # putting this here so i can use _pyi
    if windows:
        def add_entry(button: str):
            app.hideSubWindow('ctxmenu-window')
            app.hideSubWindow('extras')
            if button == 'Add entry':
                add_reg(_used_pyinstaller)
            elif button == 'Remove entry':
                del_reg()

        with app.subWindow('ctxmenu-window', 'fuse-3ds', modal=True, blocking=True):
            msg = ('A new entry can be added to the Windows context menu when you\n'
                   'right-click on a file, providing an easy way to mount various files\n'
                   'in Windows Explorer using fuse-3ds.\n'
                   '\n'
                   'This will modify the registry to add it.')
            if _pyi:
                msg += (' If you move or rename the EXE,\n'
                        'you will need to re-add the entry.')
            app.addLabel('extras-ctxmenu-label', msg)
            app.addButtons(['Add entry', 'Remove entry', 'Cancel'], add_entry, colspan=3)
            app.setResizable(False)

    # kinda lame way to prevent a resize bug
    def sh():
        if to_use == 'default':
            app.queueFunction(app.showFrame, 'default')
        else:
            app.setOptionBox('TYPE', mount_type)
        app.queueFunction(app.hideFrame, 'loading')

    app.thread(sh)

    app.go()
    stop_mount()
    return 0
