# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import tkinter as tk
import tkinter.ttk as ttk
from typing import TYPE_CHECKING

from .confighandler import get_bool, set_bool
from .optionsframes import CheckbuttonContainer

if TYPE_CHECKING:
    from . import NinfsGUI

# update options
CHECK_ONLINE = 'Check for updates on GitHub'


class NinfsSettings(tk.Toplevel):
    def __init__(self, parent: 'NinfsGUI'):
        super().__init__(parent)
        self.parent = parent

        self.wm_withdraw()
        self.wm_iconbitmap(self.parent.ico_path)
        self.wm_transient(self.parent)
        self.grab_set()
        self.wm_title('Settings')

        outer_container = ttk.Frame(self)
        outer_container.pack()

        update_check_frame = ttk.LabelFrame(outer_container, text='Updates')
        update_check_frame.pack(padx=10, pady=10)

        update_options = [CHECK_ONLINE]
        enabled = []
        if get_bool('update', 'onlinecheck'):
            enabled.append(CHECK_ONLINE)
        self.update_options_frame = CheckbuttonContainer(update_check_frame, options=update_options, enabled=enabled)
        self.update_options_frame.pack(padx=5, pady=5)

        footer_buttons = ttk.Frame(outer_container)
        footer_buttons.pack(padx=10, pady=(0, 10), side=tk.RIGHT)

        ok_button = ttk.Button(footer_buttons, text='OK', command=self.ok)
        ok_button.pack(side=tk.RIGHT)

        cancel_button = ttk.Button(footer_buttons, text='Cancel', command=self.cancel)
        cancel_button.pack(side=tk.RIGHT)

        self.wm_protocol('WM_DELETE_WINDOW', self.cancel)

        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))

        self.wm_deiconify()

    def cancel(self):
        self.destroy()

    def ok(self):
        values = self.update_options_frame.get_values()
        set_bool('update', 'onlinecheck', values[CHECK_ONLINE])
        self.destroy()
