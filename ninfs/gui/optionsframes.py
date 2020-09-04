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
    def __init__(self, parent: 'tk.BaseWidget' = None, *, options: 'List[str]'):
        super().__init__(parent)

        self.variables = {}
        for opt in options:
            var = tk.BooleanVar(self)
            cb = ttk.Checkbutton(self, variable=var, text=opt)
            cb.pack(side=tk.LEFT)

            self.variables[opt] = var

    def get_values(self) -> 'Dict[str, bool]':
        return {x: y.get() for x, y in self.variables.items()}