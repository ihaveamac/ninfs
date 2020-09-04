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


class CCISetup(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer'):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        def callback(*_):
            main_file = self.main_textbox_var.get().strip()
            b9_file = self.b9_textbox_var.get().strip()
            self.wizardcontainer.set_next_enabled(main_file and b9_file)

        main_container, main_textbox, main_textbox_var = self.make_file_picker('Select the 3DS/CCI file:',
                                                                               'Select 3DS/CCI file')
        main_container.pack(fill=tk.X, expand=True)

        b9_container, b9_textbox, b9_textbox_var = self.make_file_picker('Select the boot9 file:', 'Select boot9 file')
        b9_container.pack(fill=tk.X, expand=True)

        self.main_textbox_var = main_textbox_var
        self.b9_textbox_var = b9_textbox_var

        main_textbox_var.trace_add('write', callback)
        b9_textbox_var.trace_add('write', callback)

        b9_textbox_var.set(supportfiles.last_b9_file)

        self.set_header_suffix('3DS/CCI')

    def next_pressed(self):
        main_file = self.main_textbox_var.get().strip()
        b9_file = self.b9_textbox_var.get().strip()

        if b9_file:
            supportfiles.last_b9_file = b9_file

        args = ['cci', main_file]
        if b9_file:
            args += ['--boot9', b9_file]

        self.wizardcontainer.show_mount_point_selector('3DS/CCI', args)
