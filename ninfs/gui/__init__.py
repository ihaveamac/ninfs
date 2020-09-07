# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import sys
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as mb
import webbrowser
from inspect import cleandoc
from os.path import dirname, join
from pprint import pformat
from subprocess import Popen, PIPE, STDOUT, TimeoutExpired, check_call
from threading import Thread
from typing import TYPE_CHECKING
from uuid import uuid4

from .about import NinfsAbout
from .confighandler import get_bool, set_bool
from .settings import NinfsSettings
from .typeinfo import mount_types, ctr_types, twl_types, hac_types, uses_directory
from .updatecheck import thread_update_check
from .wizardcontainer import WizardContainer, WizardTypeSelector, WizardFailedMount

if TYPE_CHECKING:
    from typing import Callable, Dict, List, Tuple

tutorial_url = 'https://gbatemp.net/threads/499994/'

is_windows = sys.platform == 'win32'
is_mac = sys.platform == 'darwin'

# cx_Freeze, PyInstaller, etc.
frozen = getattr(sys, 'frozen', None)

if is_windows:
    from os.path import isdir as check_mountpoint
    from signal import CTRL_BREAK_EVENT
    from subprocess import CREATE_NEW_PROCESS_GROUP
else:
    from os.path import ismount as check_mountpoint


def thread_output_reader(gui: 'NinfsGUI', proc: 'Popen', uuid: 'str', output_list: 'List[str]'):
    while proc.poll() is None:
        for line in proc.stdout:
            if line != '':
                line = line.rstrip('\r\n')
                output_list.append(line)

    # if the uuid is not in the mounts dict, then it was killed by this script
    if proc.returncode and uuid in gui.mounts:
        gui.remove_mount_info(uuid)
        wizard_window = WizardContainer(gui)
        wizard_window.change_frame(WizardFailedMount, returncode=proc.returncode, output=output_list, kind='crash')
        wizard_window.focus()


class NinfsGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.mounts: Dict[str, Tuple[Popen, Thread, List[str], str]] = {}

        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        self.wm_title('ninfs')

        self.ico_path = join(dirname(__file__), 'data', 'windows.ico')
        self.wm_iconbitmap(self.ico_path)

        self.wm_minsize(500, 300)
        self.create_menu_bar()

        style = ttk.Style(container)
        style.configure('TMenubutton', background='gainsboro')

        container.rowconfigure(0, weight=0)
        container.rowconfigure(1, weight=1)
        container.rowconfigure(2, weight=0)
        container.columnconfigure(0, weight=1)

        header = ttk.Label(container, text='Mounted contents', font=(None, 15, 'bold'), justify=tk.LEFT)
        header.grid(row=0, column=0, padx=10, pady=8, sticky=tk.W)

        mount_treeview_frame = ttk.Frame(container)
        mount_treeview_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=10)
        mount_treeview_frame.rowconfigure(0, weight=1)
        mount_treeview_frame.columnconfigure(0, weight=1)
        mount_treeview_frame.columnconfigure(1, weight=0)

        self.mount_treeview = ttk.Treeview(mount_treeview_frame)
        self.mount_treeview.grid(row=0, column=0, sticky=tk.NSEW)
        self.mount_treeview.configure(columns=('mount_path', 'mount_type', 'mounted_item'), show='headings')

        self.mount_treeview.column('mount_path', width=100, anchor=tk.W)
        self.mount_treeview.heading('mount_path', text='Mount Path')
        self.mount_treeview.column('mount_type', width=50, anchor=tk.W)
        self.mount_treeview.heading('mount_type', text='Type')
        self.mount_treeview.column('mounted_item', width=200, anchor=tk.W)
        self.mount_treeview.heading('mounted_item', text='Mounted Content')

        mount_treeview_scrollbar = ttk.Scrollbar(mount_treeview_frame, orient=tk.VERTICAL,
                                                 command=self.mount_treeview.yview)
        self.mount_treeview.configure(yscrollcommand=mount_treeview_scrollbar.set)
        mount_treeview_scrollbar.grid(row=0, column=1, sticky=tk.NS)

        actions_frame = ttk.Frame(container)
        actions_frame.grid(row=2, column=0, padx=10, pady=10, sticky=tk.W)

        new_mount_button = ttk.Button(actions_frame, text='New mount', command=self.show_wizard)
        new_mount_button.pack(side=tk.LEFT)

        unmount = ttk.Button(actions_frame, text='Unmount selected', command=self.unmount_selected)
        unmount.pack(side=tk.LEFT)

        self.wm_protocol('WM_DELETE_WINDOW', self.on_close)

    def mainloop(self, n=0):
        if not get_bool('internal', 'askedonlinecheck'):
            message = '''
            Check for updates online?
            This will make a request to GitHub every time the ninfs gui is opened.
            
            This can be changed any time in Settings.
            '''
            if mb.askyesno('Check for updates', cleandoc(message)):
                set_bool('update', 'onlinecheck', True)
            set_bool('internal', 'askedonlinecheck', True)

        if get_bool('update', 'onlinecheck'):
            update_thread = Thread(target=thread_update_check, args=(self,))
            update_thread.start()
        super().mainloop(n)

    def on_close(self):
        self.unmount_all(force=True)
        self.destroy()

    def show_settings(self):
        settings_window = NinfsSettings(self)
        settings_window.focus()

    def show_wizard(self):
        wizard_window = WizardContainer(self)
        wizard_window.change_frame(WizardTypeSelector)
        wizard_window.focus()

    def mount(self, mounttype: 'str', cmdargs: 'List[str]', mountpoint: str, callback_success: 'Callable',
              callback_failed: 'Callable'):
        args = [sys.executable]
        if not frozen:
            args.append(dirname(dirname(__file__)))
        args.extend(cmdargs)
        args.append('-f')
        args.append(mountpoint)

        popen_opts = {}
        if is_windows:
            popen_opts['creationflags'] = CREATE_NEW_PROCESS_GROUP

        uuid = str(uuid4())

        output_list = ['Command: ' + pformat(args), '']
        proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=STDOUT, encoding='utf-8', **popen_opts)
        thread = Thread(target=thread_output_reader, args=(self, proc, uuid, output_list))

        mount_info = (proc, thread, output_list, mountpoint)

        def check_loop():
            if check_mountpoint(mountpoint):
                self.mount_treeview.insert('', tk.END, text=uuid, iid=uuid, values=(mountpoint, mounttype, cmdargs[1]))
                self.mounts[uuid] = mount_info
                callback_success()
                return
            if proc.poll() is not None:
                thread.join()
                callback_failed(proc.returncode, output_list)
                return

            self.after(500, check_loop)

        thread.start()

        self.after(500, check_loop)

    def unmount_selected(self):
        # the mounts dict gets modified during iteration, so the list of keys is cloned to prevent issues
        # it's also done in reverse, since later mounts might be based on earlier ones
        selection = self.mount_treeview.selection()
        for s in reversed(selection):
            self.unmount(s)

    def unmount_all(self, *, force: bool = False):
        # the mounts dict gets modified during iteration, so the list of keys is cloned to prevent issues
        # it's also done in reverse, since later mounts might be based on earlier ones
        for uuid in reversed(self.mount_treeview.get_children()):
            self.unmount(uuid, force=force)

    def remove_mount_info(self, uuid: str):
        self.mount_treeview.delete(uuid)
        del self.mounts[uuid]

    def unmount(self, uuid: 'str', *, force: bool = False):
        mount_info = self.mounts[uuid]
        if is_windows:
            mount_info[0].send_signal(CTRL_BREAK_EVENT)
            try:
                mount_info[0].wait(3)
            except TimeoutExpired:
                if force:
                    self.remove_mount_info(uuid)
                    mount_info[0].kill()
                else:
                    res = mb.askyesno('Mount not responding', 'The mount subprocess is not responding.\nTerminate it?')
                    if res:
                        self.remove_mount_info(uuid)
                        mount_info[0].kill()
            else:
                self.remove_mount_info(uuid)
        else:
            # I think this is cheating
            if is_mac:
                check_call(['diskutil', 'unmount', mount_info[3]])
                self.remove_mount_info(uuid)
            else:
                # assuming linux or bsd, which have fusermount
                check_call(['fusermount', '-u', mount_info[3]])
                self.remove_mount_info(uuid)

    @staticmethod
    def show_tutorial():
        webbrowser.open(tutorial_url)

    def show_about(self):
        about_window = NinfsAbout(self)
        about_window.focus()

    def create_menu_bar(self):
        self.option_add('*tearOff', tk.FALSE)
        menubar = tk.Menu(self)

        if is_mac:
            apple_menu = tk.Menu(menubar, name='apple')
            apple_menu.add_command(label='About ninfs', command=self.show_about)
            apple_menu.add_separator()
            menubar.add_cascade(menu=apple_menu)

            self.createcommand('tk::mac::ShowPreferences', self.show_settings)

        file_menu = tk.Menu(menubar)
        if not is_mac:
            file_menu.add_command(label='Settings', command=self.show_settings)

        help_menu = tk.Menu(menubar)
        help_menu.add_command(label='Open tutorial on GBAtemp', command=self.show_tutorial)
        if not is_mac:
            help_menu.add_command(label='About ninfs', command=self.show_about)

        menubar.add_cascade(label='File', menu=file_menu)
        menubar.add_cascade(label='Help', menu=help_menu)

        self.configure(menu=menubar)


def start_gui():
    window = NinfsGUI()

    if is_windows:
        from ctypes import windll, get_last_error
        from os import environ, getpid

        environ['NINFS_GUI_PARENT_PID'] = str(getpid())

        if not windll.kernel32.GetConsoleWindow():
            # if there is no console, make one and hide it
            # this is not an elegant solution but it lets us use send_signal on subprocesses
            if not windll.kernel32.AllocConsole():
                # AllocConsole fails when I'm testing in PyCharm but get_last_error returns 0, meaning it succeeded.
                # I don't know why this happens.
                err = get_last_error()
                if err:
                    print('Failed to use AllocConsole:', err)
            else:
                windll.user32.ShowWindow(windll.kernel32.GetConsoleWindow(), 0)  # SW_HIDE

    window.mainloop()

    return 0
