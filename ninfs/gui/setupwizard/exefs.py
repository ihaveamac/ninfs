# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import tkinter as tk
from typing import TYPE_CHECKING

from .base import WizardBase

if TYPE_CHECKING:
    from .. import WizardContainer


class ExeFSSetup(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer'):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        def callback(*_):
            main_file = self.main_textbox_var.get().strip()
            self.wizardcontainer.set_next_enabled(main_file)

        main_container, main_textbox, main_textbox_var = self.make_file_picker('Select the ExeFS file:',
                                                                               'Select ExeFS file')
        main_container.pack(fill=tk.X, expand=True)

        self.main_textbox_var = main_textbox_var

        main_textbox_var.trace_add('write', callback)

        self.set_header_suffix('ExeFS')

    def next_pressed(self):
        main_file = self.main_textbox_var.get().strip()

        args = ['exefs', main_file]

        self.wizardcontainer.show_mount_point_selector('ExeFS', args)
