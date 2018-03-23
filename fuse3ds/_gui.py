# not very good with gui development...
# don't read this file, it sucks

import signal
import subprocess
import webbrowser
from sys import executable, platform
from os import kill
from os.path import isfile

from appJar import gui

from __init__ import __version__
from pyctr.util import config_dirs

b9_paths = ('boot9.bin', 'boot9_prot.bin',
            config_dirs[0] + '/boot9.bin', config_dirs[0] + '/boot9_prot.bin',
            config_dirs[1] + '/boot9.bin', config_dirs[1] + '/boot9_prot.bin')

for p in b9_paths:
    if isfile(p):
        b9_found = True
        break
else:
    b9_found = False

# types
CCI = 'CTR Cart Image (".3ds", ".cci")'
CDN = 'CDN contents'
CIA = 'CTR Importable Archive (".cia")'
EXEFS = 'Executable Filesystem (".exefs", "exefs.bin")'
NAND = 'NAND backup ("nand.bin")'
NCCH = 'NCCH (".cxi", ".cfa", ".ncch", ".app")'
ROMFS = 'Read-only Filesystem (".romfs", "romfs.bin")'
SD = 'SD Card Contents ("Nintendo 3DS" from an SD card)'
TITLEDIR = 'Titles directory ("title" from NAND or SD)'

mount_types = {CCI: 'cci', CDN: 'cdn', CIA: 'cia', EXEFS: 'exefs', NAND: 'nand', NCCH: 'ncch', ROMFS: 'romfs', SD: 'sd',
               TITLEDIR: 'titledir'}

windows = platform == 'win32'  # only for native windows, not cygwin
if windows:
    # https://stackoverflow.com/questions/827371/is-there-a-way-to-list-all-the-available-drive-letters-in-python
    from string import ascii_uppercase
    from ctypes import windll

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

process = None  # type: Popen
curr_mountpoint = None  # type: str

app = gui('fuse-3ds ' + __version__, (380, 265))


def run_mount(module_type: str, item: str, mountpoint: str, extra_args: list = ()):
    global process, curr_mountpoint
    if process is None or process.returncode is not None:
        args = [executable, '-mfuse3ds', module_type, '-f', item, mountpoint, *extra_args]
        curr_mountpoint = mountpoint
        print('Running:', args)
        opts = {}
        if windows:
            opts['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(args, **opts)


def stop_mount():
    global process
    if process is not None and process.returncode is None:
        print('Stopping')
        if windows:
            kill(process.pid, signal.CTRL_BREAK_EVENT)
        else:
            # this is cheating...
            if platform == 'darwin':
                subprocess.check_call(['diskutil', 'unmount', curr_mountpoint])
            else:
                # assuming linux or bsd, which have fusermount
                # TODO: test this
                subprocess.check_call(['fusermount', '-u', curr_mountpoint])


def press(button: str):
    if button == 'Mount':
        extra_args = []
        mount_type = app.getOptionBox('TYPE')
        app.disableButton('Mount')
        item = app.getEntry(mount_type + 'item')
        if mount_type == NAND:
            otp = app.getEntry(NAND + 'otp')
            cid = app.getEntry(NAND + 'cid')
            aw = app.getCheckBox(NAND + 'aw')
            if otp:
                extra_args.extend(('--otp', otp))
            if cid:
                extra_args.extend(('--cid', cid))
            if aw:
                extra_args.append('-r')
        elif mount_type == SD:
            movable = app.getEntry(SD + 'movable')
            aw = app.getCheckBox(SD + 'aw')
            extra_args.extend(('--movable', movable))
            if not aw:
                extra_args.append('-r')
        mountpoint = app.getOptionBox('mountpoint') if windows else app.getEntry('mountpoint')
        run_mount(mount_types[mount_type], item, mountpoint, extra_args)
        app.enableButton('Unmount')
    elif button == 'Unmount':
        app.disableButton('Unmount')
        stop_mount()
        app.enableButton('Mount')
    elif button == 'GitHub repository':
        webbrowser.open('https://github.com/ihaveamac/fuse-3ds')


def change(*_):
    mount_type = app.getOptionBox('TYPE')
    for t in mount_types:
        if t == mount_type:
            app.showFrame(t)
        else:
            app.hideFrame(t)


# TODO: disable Mount for certain types if boot9 is not found
# TODO: SeedDB stuff
# TODO: display exceptions in a dialog if any appears

with app.frame(CCI, row=1, colspan=3):
    app.addLabel(CCI + 'label1', 'File', row=0, column=0)
    app.addFileEntry(CCI + 'item', row=0, column=1)

with app.frame(CDN, row=1, colspan=3):
    app.addLabel(CDN + 'label1', 'Directory', row=0, column=0)
    app.addDirectoryEntry(CDN + 'item', row=0, column=1)
app.hideFrame(CDN)

with app.frame(CIA, row=1, colspan=3):
    app.addLabel(CIA + 'label1', 'File', row=0, column=0)
    app.addFileEntry(CIA + 'item', row=0, column=1)
app.hideFrame(CIA)

with app.frame(EXEFS, row=1, colspan=3):
    app.addLabel(EXEFS + 'label1', 'File', row=0, column=0)
    app.addFileEntry(EXEFS + 'item', row=0, column=1)
app.hideFrame(EXEFS)

with app.frame(NAND, row=1, colspan=3):
    app.addLabel(NAND + 'label1', 'File', row=0, column=0)
    app.addFileEntry(NAND + 'item', row=0, column=1)
    app.addLabel(NAND + 'label2', 'OTP file*', row=2, column=0)
    app.addFileEntry(NAND + 'otp', row=2, column=1)
    app.addLabel(NAND + 'label3', 'CID file*', row=3, column=0)
    app.addFileEntry(NAND + 'cid', row=3, column=1)
    app.addLabel(NAND + 'label4', '*Not required if backup has essential.exefs from GodMode9.', row=4, colspan=3)
    app.addLabel(NAND + 'label5', 'Allow writing', row=5, column=0)
    app.addNamedCheckBox('', NAND + 'aw', row=5, column=1)
app.hideFrame(NAND)

with app.frame(NCCH, row=1, colspan=3):
    app.addLabel(NCCH + 'label1', 'File', row=0, column=0)
    app.addFileEntry(NCCH + 'item', row=0, column=1)
app.hideFrame(NCCH)

with app.frame(ROMFS, row=1, colspan=3):
    app.addLabel(ROMFS + 'label1', 'File', row=0, column=0)
    app.addFileEntry(ROMFS + 'item', row=0, column=1)
app.hideFrame(ROMFS)

with app.frame(SD, row=1, colspan=3):
    app.addLabel(SD + 'label1', 'Directory', row=0, column=0)
    app.addDirectoryEntry(SD + 'item', row=0, column=1)
    app.addLabel(SD + 'label2', 'movable.sed', row=2, column=0)
    app.addFileEntry(SD + 'movable', row=2, column=1)
    app.addLabel(SD + 'label3', 'Allow writing', row=3, column=0)
    app.addNamedCheckBox('', SD + 'aw', row=3, column=1)
app.hideFrame(SD)

with app.frame(TITLEDIR, row=1, colspan=3):
    app.addLabel(TITLEDIR + 'label1', 'Directory', row=0, column=0)
    app.addDirectoryEntry(TITLEDIR + 'item', row=0, column=1)
app.hideFrame(TITLEDIR)

app.setSticky('new')
app.addOptionBox('TYPE', mount_types, row=0, colspan=3)
app.setOptionBoxChangeFunction('TYPE', change)

app.setSticky('sew')
if windows:
    app.addLabel('mountlabel', 'Drive letter', row=2, column=0)
    app.addOptionBox('mountpoint', ['WWWW'], row=2, column=1) # putting "WWWW" to avoid a warning
    # noinspection PyUnboundLocalVariable
    update_drives()
else:
    app.addLabel('mountlabel', 'Mount point', row=2, column=0)
    app.addDirectoryEntry('mountpoint', row=2, column=1)

app.addButtons(['Mount', 'Unmount', 'GitHub repository'], press, row=3, colspan=3)
app.disableButton('Unmount')

app.setFont(10)


def main():
    app.go()
    stop_mount()
    return 0
