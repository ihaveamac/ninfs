# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import tkinter as tk
import tkinter.ttk as ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Dict, List, Tuple


class CheckbuttonContainer(ttk.Frame):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, options: 'List[str]', enabled: 'List[str]' = None):
        super().__init__(parent)
        if not enabled:
            enabled = []

        self.variables = {}
        for opt in options:
            var = tk.BooleanVar(self)
            cb = ttk.Checkbutton(self, variable=var, text=opt)
            cb.pack(side=tk.LEFT)
            if opt in enabled:
                var.set(True)

            self.variables[opt] = var

    def get_values(self) -> 'Dict[str, bool]':
        return {x: y.get() for x, y in self.variables.items()}


class RadiobuttonContainer(ttk.Frame):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, options: 'List[Tuple[str, str]]',
                 default: 'str'):
        super().__init__(parent)

        self.variable = tk.StringVar(self)
        for idx, opt in enumerate(options):
            rb = ttk.Radiobutton(self, variable=self.variable, text=opt[0], value=opt[1])
            rb.grid(row=idx, column=0, sticky=tk.W)

        self.variable.set(default)

    def get_selected(self):
        return self.variable.get()
