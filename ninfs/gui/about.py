# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import sys
import tkinter as tk
import tkinter.ttk as ttk

from .osver import get_os_ver
# "from .. import" didn't work :/
from __init__ import __copyright__ as ninfs_copyright
from __init__ import __version__ as ninfs_version

pad = 10

python_version = sys.version.split()[0]
os_ver = get_os_ver()


class NinfsAbout(tk.Toplevel):
    def __init__(self, parent: 'tk.Wm' = None):
        super().__init__(parent)
        self.parent = parent

        self.wm_title('About ninfs')
        self.wm_resizable(width=tk.FALSE, height=tk.FALSE)

        header_label = ttk.Label(self, text=f'ninfs {ninfs_version}', font=(None, 15, 'bold'))
        header_label.grid(row=0, column=0, padx=pad, pady=pad, sticky=tk.W)

        copyright_label = ttk.Label(self, text=ninfs_copyright)
        copyright_label.grid(row=1, column=0, padx=pad, pady=(0, pad), sticky=tk.W)

        info_label = ttk.Label(self, text=f'Running on Python {python_version}\n' + os_ver)
        info_label.grid(row=2, column=0, padx=pad, pady=(0, pad), sticky=tk.W)
