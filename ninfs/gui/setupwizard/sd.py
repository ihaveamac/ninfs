# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import tkinter as tk
from typing import TYPE_CHECKING

from .base import WizardBase
from .. import supportfiles

if TYPE_CHECKING:
    from .. import WizardContainer


class SDFilesystemSetup(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer'):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        def callback(*_):
            main_file = self.main_textbox_var.get().strip()
            b9_file = self.b9_textbox_var.get().strip()
            movable_file = self.movable_textbox_var.get().strip()
            self.wizardcontainer.set_next_enabled(main_file and b9_file and movable_file)

        labeltext = 'Select the "Nintendo 3DS" directory:'
        main_container, main_textbox, main_textbox_var = self.make_directory_picker(labeltext,
                                                                                    'Select "Nintendo 3DS" directory')
        main_container.pack(fill=tk.X, expand=True)

        b9_container, b9_textbox, b9_textbox_var = self.make_file_picker('Select the boot9 file:', 'Select boot9 file')
        b9_container.pack(fill=tk.X, expand=True)

        movable_container, movable_textbox, movable_textbox_var = self.make_file_picker('Select the movable.sed file:',
                                                                                        'Select movable.sed file')
        movable_container.pack(fill=tk.X, expand=True)

        self.options_frame = self.make_checkbox_options('Options:', ['Allow writing'])
        self.options_frame.pack(fill=tk.X, expand=True)

        self.main_textbox_var = main_textbox_var
        self.b9_textbox_var = b9_textbox_var
        self.movable_textbox_var = movable_textbox_var

        main_textbox_var.trace_add('write', callback)
        b9_textbox_var.trace_add('write', callback)
        movable_textbox_var.trace_add('write', callback)

        b9_textbox_var.set(supportfiles.last_b9_file)

        self.set_header_suffix('Nintendo 3DS SD Card')

    def next_pressed(self):
        main_file = self.main_textbox_var.get().strip()
        b9_file = self.b9_textbox_var.get().strip()
        movable_file = self.movable_textbox_var.get().strip()

        if b9_file:
            supportfiles.last_b9_file = b9_file

        args = ['sd', main_file]
        opts = self.options_frame.get_values()
        if not opts['Allow writing']:
            args.append('-r')
        if b9_file:
            args += ['--boot9', b9_file]
        if movable_file:
            args += ['--movable', movable_file]

        self.wizardcontainer.show_mount_point_selector('3DS SD', args)
