# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import sys
import tkinter as tk
import tkinter.ttk as ttk
import webbrowser
from os.path import join
from typing import TYPE_CHECKING

from Cryptodome import __version__ as pycryptodomex_version
from pyctr import __version__ as pyctr_version

from .osver import get_os_ver
# "from .. import" didn't work :/
from __init__ import __copyright__ as ninfs_copyright
from __init__ import __version__ as ninfs_version

if TYPE_CHECKING:
    from . import NinfsGUI

pad = 10

python_version = sys.version.split()[0]
pybits = 64 if sys.maxsize > 0xFFFFFFFF else 32
os_ver = get_os_ver()


class LicenseViewer(ttk.Frame):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, text: str):
        super().__init__(parent)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL)
        scrollbar.grid(row=0, column=1, sticky=tk.NSEW)

        textarea = tk.Text(self, wrap='word', yscrollcommand=scrollbar.set)
        textarea.grid(row=0, column=0, sticky=tk.NSEW)

        scrollbar.configure(command=textarea.yview)

        textarea.insert(tk.END, text)

        textarea.configure(state=tk.DISABLED)


class NinfsAbout(tk.Toplevel):
    def __init__(self, parent: 'NinfsGUI' = None):
        super().__init__(parent)
        self.parent = parent

        self.wm_withdraw()
        self.parent.set_icon(self)
        self.wm_transient(self.parent)

        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        self.wm_title('About ninfs')
        self.wm_resizable(width=tk.FALSE, height=tk.FALSE)

        header_label = ttk.Label(container, text=f'ninfs {ninfs_version}', font=(None, 15, 'bold'))
        header_label.grid(row=0, column=0, padx=pad, pady=pad, sticky=tk.W)

        version_label = ttk.Label(container, text=f'Running on {python_version} {pybits}-bit')
        version_label.grid(row=1, column=0, padx=pad, pady=(0, pad), sticky=tk.W)

        copyright_label = ttk.Label(container, text='This program uses several libraries and modules, which have '
                                                    'their licenses below.')
        copyright_label.grid(row=2, column=0, padx=pad, pady=(0, pad), sticky=tk.W)

        # tab name, license file name, url
        info = [
            (f'ninfs {ninfs_version}', 'ninfs.md', 'https://github.com/ihaveamac/ninfs',
             'ninfs - Copyright (c) 2017-2021 Ian Burgwin'),
            (f'WinFsp 2020.2', 'winfsp.txt', 'https://github.com/billziss-gh/winfsp',
             'WinFsp - Windows File System Proxy, Copyright (C) Bill Zissimopoulos'),
            (f'pycryptodomex {pycryptodomex_version}', 'pycryptodome.rst',
             'https://github.com/Legrandin/pycryptodome', 'PyCryptodome - multiple licenses'),
            (f'pyctr {pyctr_version}', 'pyctr', 'https://github.com/ihaveamac/pyctr',
             'pyctr - Copyright (c) 2017-2021 Ian Burgwin'),
            ('haccrypto 0.1.2', 'haccrypto.md', 'https://github.com/luigoalma/haccrypto',
             'haccrypto - Copyright (c) 2017-2021 Ian Burgwin & Copyright (c) 2020-2021 Luis Marques')
        ]

        license_notebook = ttk.Notebook(container)
        license_notebook.grid(row=3, column=0, padx=pad, pady=(0, pad))

        def cmd_maker(do_url):
            def func():
                webbrowser.open(do_url)
            return func

        for tab_name, license_file, url, header in info:
            print([tab_name, license_file, url])
            frame = ttk.Frame(license_notebook)
            license_notebook.add(frame, text=tab_name)

            license_header_label = ttk.Label(frame, text=header)
            license_header_label.grid(row=0, sticky=tk.W, padx=pad//2, pady=pad//2)

            url_button = ttk.Button(frame,
                                    text='Open website - ' + url,
                                    command=cmd_maker(url))
            url_button.grid(row=1)

            with open(parent.get_data_file(join('licenses', license_file)), 'r', encoding='utf-8') as f:
                license_frame = LicenseViewer(frame, text=f.read())
                license_frame.grid(row=2)

        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))

        self.wm_deiconify()
