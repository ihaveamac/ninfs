# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.filedialog as fd
from typing import TYPE_CHECKING

from ..optionsframes import CheckbuttonContainer

if TYPE_CHECKING:
    from typing import List, Tuple
    from ..wizardcontainer import WizardContainer


class WizardBase(ttk.Frame):
    def __init__(self, parent: 'tk.BaseWidget' = None, *args, wizardcontainer: 'WizardContainer', **kwargs):
        super().__init__(parent)
        self.parent = parent
        self.wizardcontainer = wizardcontainer

    def next_pressed(self):
        print('This should not be seen')

    def set_header(self, text: str):
        self.wizardcontainer.header.configure(text=text)

    def set_header_suffix(self, text: str):
        self.set_header('Mount new content - ' + text)

    def make_container(self, labeltext: str) -> 'ttk.Frame':
        container = ttk.Frame(self)

        container.rowconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=0)

        label = ttk.Label(container, text=labeltext, justify=tk.LEFT)
        label.grid(row=0, column=0, columnspan=2, pady=(4, 0), sticky=tk.EW)

        return container

    def make_entry(self, labeltext: str, default: str = None) -> 'Tuple[ttk.Frame, ttk.Entry, tk.StringVar]':
        container = self.make_container(labeltext)

        textbox_var = tk.StringVar(self)

        textbox = ttk.Entry(container, textvariable=textbox_var)
        textbox.grid(row=1, column=0, columnspan=2, pady=4, sticky=tk.EW)

        if default:
            textbox_var.set(default)

        return container, textbox, textbox_var

    def make_file_picker(self, labeltext: str, fd_title: str,
                         default: str = None) -> 'Tuple[ttk.Frame, ttk.Entry, tk.StringVar]':
        container = self.make_container(labeltext)

        textbox_var = tk.StringVar(self)

        textbox = ttk.Entry(container, textvariable=textbox_var)
        textbox.grid(row=1, column=0, pady=4, sticky=tk.EW)

        if default:
            textbox_var.set(default)

        def choose_file():
            f = fd.askopenfilename(parent=self.parent, title=fd_title)
            if f:
                textbox_var.set(f)

        filepicker_button = ttk.Button(container, text='...', command=choose_file)
        filepicker_button.grid(row=1, column=1, pady=4)

        return container, textbox, textbox_var

    def make_directory_picker(self, labeltext: str, fd_title: str,
                              default: str = None) -> 'Tuple[ttk.Frame, ttk.Entry, tk.StringVar]':
        container = self.make_container(labeltext)

        textbox_var = tk.StringVar(self)

        textbox = ttk.Entry(container, textvariable=textbox_var)
        textbox.grid(row=1, column=0, pady=4, sticky=tk.EW)

        if default:
            textbox_var.set(default)

        def choose_file():
            f = fd.askdirectory(parent=self.parent, title=fd_title)
            if f:
                textbox_var.set(f)

        directorypicker_button = ttk.Button(container, text='...', command=choose_file)
        directorypicker_button.grid(row=1, column=1, pady=4)

        return container, textbox, textbox_var

    def make_option_menu(self, labeltext: str, *options) -> 'Tuple[ttk.Frame, ttk.OptionMenu, tk.StringVar]':
        container = self.make_container(labeltext)

        optionmenu_variable = tk.StringVar(self)

        default = None
        if options:
            default = options[0]

        optionmenu = ttk.OptionMenu(container, optionmenu_variable, default, *options)
        optionmenu.grid(row=1, column=0, columnspan=2, pady=4, sticky=tk.EW)

        return container, optionmenu, optionmenu_variable

    def make_checkbox_options(self, labeltext: str, options: 'List[str]'):
        container = ttk.Frame(self)
        label = ttk.Label(container, text=labeltext)
        label.grid(row=0, column=0, padx=(0, 4), sticky=tk.NW)

        cb = CheckbuttonContainer(container, options=options)
        cb.grid(row=0, column=1, sticky=tk.W)

        return container, cb
