# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import tkinter as tk
import tkinter.ttk as ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List


class OutputViewer(ttk.Frame):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, output: 'List[str]'):
        super().__init__(parent)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL)
        scrollbar.grid(row=0, column=1, sticky=tk.NSEW)

        textarea = tk.Text(self, wrap='word', yscrollcommand=scrollbar.set)
        textarea.grid(row=0, column=0, sticky=tk.NSEW)

        scrollbar.configure(command=textarea.yview)

        for line in output:
            textarea.insert(tk.END, line + '\n')

        textarea.see(tk.END)
        textarea.configure(state=tk.DISABLED)
