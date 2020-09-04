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


class CTRNandImageSetup(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer'):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        def callback(*_):
            main_file = self.main_textbox_var.get().strip()
            b9_file = self.b9_textbox_var.get().strip()
            self.wizardcontainer.set_next_enabled(main_file and b9_file)

        main_container, main_textbox, main_textbox_var = self.make_file_picker('Select the NAND file:',
                                                                               'Select NAND file')
        main_container.pack(fill=tk.X, expand=True)

        b9_container, b9_textbox, b9_textbox_var = self.make_file_picker('Select the boot9 file:', 'Select boot9 file')
        b9_container.pack(fill=tk.X, expand=True)

        labeltext = 'Select the OTP file (not required if GodMode9 essentials.exefs is embedded):'
        otp_container, otp_textbox, otp_textbox_var = self.make_file_picker(labeltext, 'Select OTP file')
        otp_container.pack(fill=tk.X, expand=True)

        options_frame, cb_container = self.make_checkbox_options('Options:', ['Allow writing'])
        options_frame.pack(fill=tk.X, expand=True)
        self.cb_container = cb_container

        self.main_textbox_var = main_textbox_var
        self.b9_textbox_var = b9_textbox_var
        self.otp_textbox_var = otp_textbox_var

        main_textbox_var.trace_add('write', callback)
        b9_textbox_var.trace_add('write', callback)

        b9_textbox_var.set(supportfiles.last_b9_file)

        self.set_header_suffix('Nintendo 3DS NAND')

    def next_pressed(self):
        main_file = self.main_textbox_var.get().strip()
        b9_file = self.b9_textbox_var.get().strip()
        otp_file = self.otp_textbox_var.get().strip()

        if b9_file:
            supportfiles.last_b9_file = b9_file

        args = ['nandctr', main_file]
        opts = self.cb_container.get_values()
        if not opts['Allow writing']:
            args.append('-r')
        if b9_file:
            args += ['--boot9', b9_file]
        if otp_file:
            args += ['--otp', otp_file]

        self.wizardcontainer.show_mount_point_selector('3DS NAND', args)
