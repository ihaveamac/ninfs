# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from datetime import datetime
from sys import platform
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.filedialog as fd
from typing import TYPE_CHECKING

from .opendir import open_directory
from .outputviewer import OutputViewer
from .setupwizard import *
from .typeinfo import mount_types, ctr_types, twl_types, hac_types

if TYPE_CHECKING:
    from typing import List, Type
    from . import NinfsGUI

wizard_bases = {
    'cci': CCISetup,
    'cdn': CDNSetup,
    'cia': CIASetup,
    'exefs': ExeFSSetup,
    'nandctr': CTRNandImageSetup,
    'nandhac': HACNandImageSetup,
    'nandtwl': TWLNandImageSetup,
    'ncch': NCCHSetup,
    'romfs': RomFSSetup,
    'sd': SDFilesystemSetup,
    'srl': SRLSetup,
    'threedsx': ThreeDSXSetup,
}

if platform == 'win32':
    from ctypes import windll
    from string import ascii_uppercase

    def get_unused_drives() -> 'List[str]':
        # https://stackoverflow.com/questions/827371/is-there-a-way-to-list-all-the-available-drive-letters-in-python
        drives = []
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in ascii_uppercase:
            if not bitmask & 1:
                drives.append(letter)
            bitmask >>= 1

        return drives


class WizardTypeSelector(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer'):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        self.current_type = ''

        container, type_selector, type_selector_var = self.make_option_menu('Select the content type:')
        type_selector_menu = type_selector['menu']

        container.pack(fill=tk.X, expand=True)

        def add_options(header, keys):
            type_selector_menu.add_command(label=header, state=tk.DISABLED)
            for k in keys:
                # This isn't very nice
                def changer(key):
                    def c():
                        self.wizardcontainer.set_next_enabled(True)
                        self.current_type = key
                        self.type_selector_var.set(mount_types[key])
                    return c
                type_selector_menu.add_command(label='  ' + mount_types[k], command=changer(k))

        add_options('Select a type', ())
        add_options('Nintendo 3DS', ctr_types)
        add_options('Nintendo DSi', twl_types)
        add_options('Nintendo Switch', hac_types)

        type_selector_var.set('Select a type')

        self.type_selector_var = type_selector_var

    def next_pressed(self):
        next_base = wizard_bases[self.current_type]
        self.wizardcontainer.change_frame(next_base)


class WizardMountPointSelector(WizardBase):

    mount_point_var: 'tk.StringVar'

    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer', mounttype: 'str',
                 cmdargs: 'List[str]'):
        super().__init__(parent, wizardcontainer=wizardcontainer)
        self.mounttype = mounttype
        self.cmdargs = cmdargs

        if platform == 'win32':
            drive_letters = [x + ':' for x in get_unused_drives()]

            container, drive_selector, drive_selector_var = self.make_option_menu('Select the drive letter to use:',
                                                                                  *drive_letters)
            container.pack(fill=tk.X, expand=True)

            self.mount_point_var = drive_selector_var

            self.wizardcontainer.set_next_enabled(True)

        else:
            def callback(*_):
                mount_point = self.mount_point_var.get().strip()
                self.wizardcontainer.set_next_enabled(mount_point)

            labeltext = 'Select the directory to mount to:'
            container, mount_textbox, mount_textbox_var = self.make_directory_picker(labeltext, 'Select mountpoint')
            container.pack(fill=tk.X, expand=True)

            mount_textbox_var.trace_add('write', callback)

            self.mount_point_var = mount_textbox_var

    def next_pressed(self):
        self.wizardcontainer.mount(self.mounttype, self.cmdargs, self.mount_point_var.get())


class WizardMountStep(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer', mounttype: 'str',
                 cmdargs: 'List[str]', mountpoint: 'str'):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        self.wizardcontainer.set_cancel_enabled(False)

        self.mountpoint = mountpoint

        label = ttk.Label(self, text='Starting mount process...')
        label.pack(fill=tk.X, expand=True)

        self.wizardcontainer.parent.mount(mounttype, cmdargs, mountpoint, self.callback_success, self.callback_failed)

    def callback_success(self):
        opened = open_directory(self.mountpoint)
        self.wizardcontainer.destroy()

    def callback_failed(self, returncode: 'int', output: 'List[str]'):
        self.wizardcontainer.change_frame(WizardFailedMount, returncode=returncode, output=output, kind='mountfail')

    def next_pressed(self):
        pass


class WizardFailedMount(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer', returncode: int,
                 output: 'List[str]', kind: str):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        output.append('')
        output.append(f'Return code was {returncode}')

        self.returncode = returncode
        self.output = output

        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        kinds = {
            'mountfail': f'Failed to mount (return code {returncode}). Output is below:',
            'crash': f'The mount subprocess crashed (return code {returncode}). Output is below:'
        }
        kinds_header = {
            'mountfail': 'Failed to mount',
            'crash': 'Mount subprocess crashed'
        }
        self.set_header(kinds_header[kind])
        label = ttk.Label(self, text=kinds[kind])
        label.grid(row=0, column=0, sticky=tk.EW)

        viewer = OutputViewer(self, output=output)
        viewer.grid(row=1, column=0, sticky=tk.NSEW)

        self.wizardcontainer.next_button.configure(text='Save output to file')

        self.wizardcontainer.set_next_enabled(True)

    def next_pressed(self):
        time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        fn = fd.asksaveasfilename(parent=self, initialfile=f'ninfs-error_{time}.log')
        if fn:
            with open(fn, 'w', encoding='utf-8') as f:
                for line in self.output:
                    f.write(line + '\n')


class WizardContainer(tk.Toplevel):
    current_frame: 'WizardBase' = None

    def __init__(self, parent: 'NinfsGUI'):
        super().__init__(parent)
        self.parent = parent

        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        self.wm_title('ninfs - Mount content')
        self.wm_minsize(500, 350)

        container.rowconfigure(0, weight=0)
        container.rowconfigure(1, weight=1)
        container.rowconfigure(2, weight=0)
        container.columnconfigure(0, weight=1)

        self.header = ttk.Label(container, text='Mount new content', font=(None, 15, 'bold'), justify=tk.LEFT)
        self.header.grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)

        self.container = ttk.Frame(container)
        self.container.grid(row=1, column=0, padx=10, sticky=tk.NSEW)

        self.footer_buttons = ttk.Frame(container)
        self.footer_buttons.grid(row=2, column=0, padx=10, pady=10, sticky=tk.E)

        def next_pressed():
            if self.current_frame:
                self.current_frame.next_pressed()

        self.next_button = ttk.Button(self.footer_buttons, text='Next', command=next_pressed)
        self.next_button.pack(side=tk.RIGHT)

        def cancel_pressed():
            self.destroy()

        self.cancel_button = ttk.Button(self.footer_buttons, text='Cancel', command=cancel_pressed)
        self.cancel_button.pack(side=tk.RIGHT)

    def set_cancel_enabled(self, status: bool):
        self.cancel_button.configure(state=tk.NORMAL if status else tk.DISABLED)

    def set_next_enabled(self, status: bool):
        self.next_button.configure(state=tk.NORMAL if status else tk.DISABLED)

    def show_mount_point_selector(self, mounttype: 'str', cmdargs: 'List[str]'):
        self.next_button.configure(text='Mount')
        self.change_frame(WizardMountPointSelector, cmdargs=cmdargs, mounttype=mounttype)

    def mount(self, mounttype: 'str', cmdargs: 'List[str]', mountpoint: str):
        self.change_frame(WizardMountStep, mounttype=mounttype, cmdargs=cmdargs, mountpoint=mountpoint)

    def change_frame(self, target: 'Type[WizardBase]', *args, **kwargs):
        if self.current_frame:
            self.current_frame.pack_forget()

        self.set_cancel_enabled(True)
        self.set_next_enabled(False)
        self.current_frame = target(self.container, wizardcontainer=self, *args, **kwargs)
        self.current_frame.pack(fill=tk.BOTH, expand=True)
