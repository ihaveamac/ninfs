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


class HACNandImageSetup(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer'):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        def callback(*_):
            main_file = self.main_textbox_var.get().strip()
            keys_file = self.keys_textbox_var.get().strip()
            self.wizardcontainer.set_next_enabled(main_file and keys_file)

        labeltext = 'Select the NAND file (full or split):'
        main_container, main_textbox, main_textbox_var = self.make_file_picker(labeltext, 'Select NAND file')
        main_container.pack(fill=tk.X, expand=True)

        keys_container, keys_textbox, keys_textbox_var = self.make_file_picker('Select the BIS keys file:',
                                                                               'Select BIS keys file')
        keys_container.pack(fill=tk.X, expand=True)

        options_frame, cb_container = self.make_checkbox_options('Options:', ['Allow writing'])
        options_frame.pack(fill=tk.X, expand=True)
        self.cb_container = cb_container

        self.main_textbox_var = main_textbox_var
        self.keys_textbox_var = keys_textbox_var

        main_textbox_var.trace_add('write', callback)
        keys_textbox_var.trace_add('write', callback)

        self.set_header_suffix('Nintendo Switch NAND')

    def next_pressed(self):
        main_file = self.main_textbox_var.get().strip()
        keys_file = self.keys_textbox_var.get().strip()

        args = ['nandhac', main_file]
        if main_file[-3] == '.':
            try:
                int(main_file[-2:])
            except ValueError:
                # not a split file
                pass
            else:
                # is a split file
                args.append('--split-files')
        opts = self.cb_container.get_values()
        if not opts['Allow writing']:
            args.append('-r')
        if keys_file:
            args += ['--keys', keys_file]

        self.wizardcontainer.show_mount_point_selector('Switch NAND', args)
