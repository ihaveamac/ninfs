# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import tkinter as tk
import tkinter.ttk as ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Dict, List


class CheckbuttonContainer(ttk.Frame):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, labeltext: 'str', options: 'List[str]'):
        super().__init__(parent)

        label = ttk.Label(self, text=labeltext, justify=tk.LEFT)
        label.grid(row=0, column=0, padx=(0, 8), sticky=tk.N)

        cb_container = ttk.Frame(self)
        cb_container.grid(row=0, column=1)

        self.variables = {}
        for idx, opt in enumerate(options):
            var = tk.BooleanVar(self)
            cb = ttk.Checkbutton(cb_container, variable=var, text=opt)
            cb.grid(row=idx, column=0, sticky=tk.W)

            self.variables[opt] = var

    def get_values(self) -> 'Dict[str, bool]':
        return {x: y.get() for x, y in self.variables.items()}