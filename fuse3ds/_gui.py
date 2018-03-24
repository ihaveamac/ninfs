# not very good with gui development...
# don't read this file, it sucks

import signal
import subprocess
import webbrowser
from sys import exit, executable, platform, version_info, maxsize
from os import kill
from os.path import isfile, isdir
from time import sleep
from traceback import print_exception

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

types_list = (CCI, CDN, CIA, EXEFS, NAND, NCCH, ROMFS, SD, TITLEDIR)

windows = platform == 'win32'  # only for native windows, not cygwin
if windows:
    from os import startfile
    from ctypes import windll
    from string import ascii_uppercase

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

process = None  # type: subprocess.Popen
curr_mountpoint = None  # type: str

app = gui('fuse-3ds ' + __version__, (380, 265))


def run_mount(module_type: str, item: str, mountpoint: str, extra_args: list = ()):
    global process, curr_mountpoint
    if process is None or process.poll() is not None:
        args = [executable, '-mfuse3ds', module_type, '-f', item, mountpoint, *extra_args]
        curr_mountpoint = mountpoint
        print('Running:', args)
        opts = {}
        if windows:
            opts['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(args, **opts)
        process.wait(3)


def stop_mount():
    global process
    if process is not None and process.poll() is None:
        print('Stopping')
        if windows:
            kill(process.pid, signal.CTRL_BREAK_EVENT)
        else:
            # this is cheating...
            if platform == 'darwin':
                subprocess.check_call(['diskutil', 'unmount', curr_mountpoint])
            else:
                # assuming linux or bsd, which have fusermount
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
        try:
            run_mount(mount_types[mount_type], item, mountpoint, extra_args)
        except subprocess.TimeoutExpired:
            # worked! maybe! if it didn't exit after 3 seconds!
            app.enableButton('Unmount')
            if windows:
                while not isdir(mountpoint):  # this must be changed if i allow dir mounting on windows
                    sleep(1)
                try:
                    subprocess.check_call(['explorer', mountpoint])
                except subprocess.CalledProcessError:
                    # not using startfile since i've been getting fatal errors (PyEval_RestoreThread) on windows
                    #   for some reason
                    pass
            return
        except Exception as e:
            print_exception(type(e), e, e.__traceback__)
        # if it didn't work...
        app.showSubWindow('mounterror')
        app.enableButton('Mount')

    elif button == 'Unmount':
        app.disableButton('Unmount')
        # noinspection PyBroadException
        try:
            stop_mount()
            app.enableButton('Mount')
        except Exception as e:
            print_exception(type(e), e, e.__traceback__)
            app.showSubWindow('unmounterror')
            app.enableButton('Unmount')
    elif button == 'GitHub repository':
        webbrowser.open('https://github.com/ihaveamac/fuse-3ds')


def kill_process(_):
    process.kill()
    app.hideSubWindow('unmounterror')
    app.enableButton('Mount')
    app.disableButton('Unmount')


def change(*_):
    mount_type = app.getOptionBox('TYPE')
    for t in mount_types:
        if t == mount_type:
            app.showFrame(t)
        else:
            app.hideFrame(t)


# TODO: disable Mount for certain types if boot9 is not found
# TODO: SeedDB stuff
# TODO: maybe check if the mount was unmounted outside of the unmount button

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
app.addOptionBox('TYPE', types_list, row=0, colspan=3)
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

with app.frame('FOOTER', row=3, colspan=3):
    app.addButtons(['Mount', 'Unmount', 'GitHub repository'], press, colspan=3)
    app.disableButton('Unmount')
    app.addHorizontalSeparator()
    app.addLabel('footer', 'fuse-3ds {0} running on Python {1[0]}.{1[1]}.{1[2]} {2} on {3}'.format(
        __version__, version_info, '64-bit' if maxsize > 0xFFFFFFFF else '32-bit', platform), colspan=3)

# app.addStatusbar()
# app.setStatusbar('Waiting')
app.setFont(10)
app.setResizable(False)

# failed to mount subwindow
with app.subWindow('mounterror', 'fuse-3ds Error', modal=True, blocking=True):
    app.addLabel('mounterror-label', 'Failed to mount. Please check the output.')
    app.addNamedButton('OK', 'mounterror-ok', lambda _: app.hideSubWindow('mounterror'))
    app.setResizable(False)

# failed to unmount subwindow
with app.subWindow('unmounterror', 'fuse-3ds Error', modal=True, blocking=True):
    def unmount_ok(_):
        app.hideSubWindow('unmounterror')
        app.enableButton('Unmount')

    app.addLabel('unmounterror-label', 'Failed to unmount. Please check the output.\n\n'
                                       'You can kill the process if it is not responding.\n'
                                       'This should be used as a last resort.'
                                       'The process should be unmounted normally.', colspan=2)
    app.addNamedButton('OK', 'unmounterror-ok', unmount_ok)
    app.addNamedButton('Kill process', 'unmounterror-kill', kill_process, row='previous', column=1)
    app.setResizable(False)


def main():
    app.go()
    stop_mount()
    return 0
