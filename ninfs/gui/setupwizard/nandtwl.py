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


class TWLNandImageSetup(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer'):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        def callback(*_):
            main_file = self.main_textbox_var.get().strip()
            self.wizardcontainer.set_next_enabled(main_file)

        main_container, main_textbox, main_textbox_var = self.make_file_picker('Select the NAND file:',
                                                                               'Select NAND file')
        main_container.pack(fill=tk.X, expand=True)

        labeltext = 'Enter the Console ID (not required if nocash footer is embedded)'
        consoleid_container, consoleid_textbox, consoleid_textbox_var = self.make_entry(labeltext)
        consoleid_container.pack(fill=tk.X, expand=True)

        options_frame, cb_container = self.make_checkbox_options('Options:', ['Allow writing'])
        options_frame.pack(fill=tk.X, expand=True)
        self.cb_container = cb_container

        self.main_textbox_var = main_textbox_var
        self.consoleid_textbox_var = consoleid_textbox_var

        main_textbox_var.trace_add('write', callback)
        consoleid_textbox_var.trace_add('write', callback)

        self.set_header_suffix('Nintendo DSi NAND')

    def next_pressed(self):
        main_file = self.main_textbox_var.get().strip()
        consoleid = self.consoleid_textbox_var.get().strip()

        args = ['nandtwl', main_file]
        opts = self.cb_container.get_values()
        if not opts['Allow writing']:
            args.append('-r')
        if consoleid:
            args += ['--console-id', consoleid]

        self.wizardcontainer.show_mount_point_selector('DSi NAND', args)
