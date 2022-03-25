# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.
import os
from datetime import datetime
from sys import platform
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
from typing import TYPE_CHECKING

import mountinfo
from .opendir import open_directory
from .optionsframes import CheckbuttonContainer, RadiobuttonContainer
from .outputviewer import OutputViewer
from .setupwizard import *

if TYPE_CHECKING:
    from typing import List, Optional, Type
    from . import NinfsGUI

# importing this from __init__ would cause a circular import, and it's just easier to copy this again
is_windows = platform == 'win32'

wizard_bases = {
    'cci': CCISetup,
    'cdn': CDNSetup,
    'cia': CIASetup,
    'exefs': ExeFSSetup,
    'nandctr': CTRNandImageSetup,
    'nandhac': HACNandImageSetup,
    'nandtwl': TWLNandImageSetup,
    'nandbb': BBNandImageSetup,
    'ncch': NCCHSetup,
    'romfs': RomFSSetup,
    'sd': SDFilesystemSetup,
    'sdtitle': SDTitleSetup,
    'srl': SRLSetup,
    'threedsx': ThreeDSXSetup,
}

if is_windows:
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
                        item_info = mountinfo.get_type_info(key)
                        label_text = f'{item_info["name"]} ({item_info["info"]})'
                        self.wizardcontainer.set_next_enabled(True)
                        self.current_type = key
                        self.type_selector_var.set(label_text)
                    return c
                item_info = mountinfo.get_type_info(k)
                label_text = f'{item_info["name"]} ({item_info["info"]})'
                type_selector_menu.add_command(label='  ' + label_text, command=changer(k))

        add_options('Select a type', ())
        for cat, types in mountinfo.categories.items():
            add_options(cat, types)

        type_selector_var.set('Select a type')

        self.type_selector_var = type_selector_var

    def next_pressed(self):
        next_base = wizard_bases[self.current_type]
        self.wizardcontainer.change_frame(next_base)


class WizardMountAdvancedOptions(tk.Toplevel):
    def __init__(self, parent: 'WizardContainer' = None, *, current: 'dict', show_dev_keys: bool):
        super().__init__(parent)

        self.wm_title('Advanced mount options')
        self.wm_resizable(width=tk.FALSE, height=tk.FALSE)

        self.wm_transient(parent)
        parent.parent.set_icon(self)
        self.grab_set()

        self.ok_clicked = False

        # prevent background issues on macOS and Linux
        outer_container = ttk.Frame(self)
        outer_container.pack(fill=tk.BOTH, expand=True)

        container = ttk.Frame(outer_container)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        if show_dev_keys:
            label_opt = ttk.Label(container, text='Options')
            label_opt.grid(row=0, column=0, padx=(0, 10), sticky=tk.NW)

            enabled = []
            if current['use_dev']:
                enabled.append('Use developer-unit keys')
            self.check_opt = CheckbuttonContainer(container, options=['Use developer-unit keys'], enabled=enabled)
            self.check_opt.grid(row=0, column=1, pady=(0, 10), sticky=tk.NW)
        else:
            self.check_opt = None

        if not is_windows:
            label_eua = ttk.Label(container, text='External user access')
            label_eua.grid(row=1, column=0, padx=(0, 8), sticky=tk.NW)

            opts_eua = [
                ("Don't allow other users", 'none'),
                ('Allow access by root (-o allow_root)', 'allow_root'),
                ('Allow access by other users (-o allow_other)', 'allow_other'),
            ]
            self.rb_container_eua = RadiobuttonContainer(container, options=opts_eua, default=current['user_access'])
            self.rb_container_eua.grid(row=1, column=1, pady=(0, 10))
        else:
            self.rb_container_eua = None

        def ok():
            self.ok_clicked = True
            self.destroy()

        ok_button = ttk.Button(container, text='OK', command=ok)
        ok_button.grid(row=2, column=0, columnspan=2)

        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))

        self.wm_deiconify()

    def get_options(self):
        user_access = 'none'
        use_dev = False
        if self.rb_container_eua:
            user_access = self.rb_container_eua.get_selected()
        if self.check_opt:
            use_dev = self.check_opt.get_values()['Use developer-unit keys']
        return {'user_access': user_access, 'use_dev': use_dev}

    def wait_for_response(self):
        self.wait_window()
        return self.ok_clicked


class WizardMountPointSelector(WizardBase):

    mount_point_var: 'tk.StringVar'

    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer', mounttype: 'str',
                 cmdargs: 'List[str]'):
        super().__init__(parent, wizardcontainer=wizardcontainer)
        self.mounttype = mounttype
        self.cmdargs = cmdargs

        self.adv_options = {'user_access': 'none', 'use_dev': False}

        # special case for nand types here, which should not be mounted to a drive letter
        if is_windows and not cmdargs[0].startswith('nand'):
            self.is_drive_letter = True

            drive_letters = [x + ':' for x in get_unused_drives()]

            container, drive_selector, drive_selector_var = self.make_option_menu('Select the drive letter to use:',
                                                                                  *drive_letters)
            container.pack(fill=tk.X, expand=True)

            self.mount_point_var = drive_selector_var

            if cmdargs[0] in mountinfo.supports_dev_keys:
                # the only advanced option for windows users is dev keys, so hide this button if that doesn't apply
                adv_options_button = ttk.Button(self, text='Advanced mount options', command=self.show_advanced_options)
                adv_options_button.pack(fill=tk.X, expand=True)

            self.wizardcontainer.set_next_enabled(True)

        else:
            self.is_drive_letter = False

            def callback(*_):
                mount_point = self.mount_point_var.get().strip()
                self.wizardcontainer.set_next_enabled(mount_point)

            labeltext = 'Select the directory to mount to:'
            container, mount_textbox, mount_textbox_var = self.make_directory_picker(labeltext, 'Select mountpoint')
            container.pack(fill=tk.X, expand=True)

            if (not is_windows) or cmdargs[0] in mountinfo.supports_dev_keys:
                # the only advanced option for windows users is dev keys, so hide this button if that doesn't apply
                adv_options_button = ttk.Button(self, text='Advanced mount options', command=self.show_advanced_options)
                adv_options_button.pack(fill=tk.X, expand=True)

            mount_textbox_var.trace_add('write', callback)

            self.mount_point_var = mount_textbox_var

    def show_advanced_options(self):
        adv_options_window = WizardMountAdvancedOptions(self.wizardcontainer, current=self.adv_options,
                                                        show_dev_keys=self.cmdargs[0] in mountinfo.supports_dev_keys)
        adv_options_window.focus_set()
        if adv_options_window.wait_for_response():
            self.adv_options.update(adv_options_window.get_options())

    def next_pressed(self):
        if is_windows and not self.is_drive_letter:
            if len(os.listdir(self.mount_point_var.get())) != 0:
                mb.showerror('ninfs', 'Directory must be empty.')
                return
        extra_args = []
        if self.adv_options['use_dev']:
            extra_args.append('--dev')
        if self.adv_options['user_access'] != 'none':
            extra_args.extend(('-o', self.adv_options['user_access']))
        self.wizardcontainer.mount(self.mounttype, self.cmdargs + extra_args, self.mount_point_var.get(),
                                   self.is_drive_letter)


class WizardMountStep(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer', mounttype: str,
                 cmdargs: 'List[str]', mountpoint: str, is_drive_letter: bool):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        self.wizardcontainer.set_cancel_enabled(False)

        self.mountpoint = mountpoint

        label = ttk.Label(self, text='Starting mount process...')
        label.pack(fill=tk.X, expand=True)

        self.wizardcontainer.parent.mount(mounttype, cmdargs, mountpoint, self.callback_success, self.callback_failed,
                                          is_drive_letter=is_drive_letter)

    def callback_success(self):
        opened = open_directory(self.mountpoint)
        self.wizardcontainer.destroy()

    def callback_failed(self, returncode: 'int', output: 'List[str]'):
        self.wizardcontainer.change_frame(WizardFailedMount, returncode=returncode, output=output, kind='mountfail')

    def next_pressed(self):
        pass


class WizardFailedMount(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer',
                 returncode: 'Optional[int]', output: 'List[str]', kind: str):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        if returncode:
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

        self.wm_withdraw()
        self.parent.set_icon(self)
        self.wm_transient(parent)

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

        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))

        self.wm_deiconify()

    def set_cancel_enabled(self, status: bool):
        self.cancel_button.configure(state=tk.NORMAL if status else tk.DISABLED)

    def set_next_enabled(self, status: bool):
        self.next_button.configure(state=tk.NORMAL if status else tk.DISABLED)

    def show_mount_point_selector(self, mounttype: 'str', cmdargs: 'List[str]'):
        self.next_button.configure(text='Mount')
        self.change_frame(WizardMountPointSelector, cmdargs=cmdargs, mounttype=mounttype)

    def mount(self, mounttype: 'str', cmdargs: 'List[str]', mountpoint: str, is_drive_letter: bool):
        self.change_frame(WizardMountStep, mounttype=mounttype, cmdargs=cmdargs, mountpoint=mountpoint,
                          is_drive_letter=is_drive_letter)

    def change_frame(self, target: 'Type[WizardBase]', *args, **kwargs):
        if self.current_frame:
            self.current_frame.pack_forget()

        self.set_cancel_enabled(True)
        self.set_next_enabled(False)
        self.current_frame = target(self.container, wizardcontainer=self, *args, **kwargs)
        self.current_frame.pack(fill=tk.BOTH, expand=True)
