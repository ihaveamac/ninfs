# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import json
import tkinter as tk
import tkinter.ttk as ttk
import webbrowser
from typing import TYPE_CHECKING
from urllib.request import urlopen, Request

from pkg_resources import parse_version

from .outputviewer import OutputViewer
from .setupwizard import WizardBase
from .wizardcontainer import WizardContainer

if TYPE_CHECKING:
    from typing import Tuple
    # noinspection PyProtectedMember
    from pkg_resources._vendor.packaging.version import Version
    from http.client import HTTPResponse

    from . import NinfsGUI

from __init__ import __version__

version: 'Version' = parse_version(__version__)


class UpdateNotificationWindow(WizardBase):
    def __init__(self, parent: 'tk.BaseWidget' = None, *, wizardcontainer: 'WizardContainer', releaseinfo: 'dict'):
        super().__init__(parent, wizardcontainer=wizardcontainer)

        self.releaseinfo = releaseinfo

        self.set_header('New update available - ' + releaseinfo['tag_name'])

        self.rowconfigure(0, weight=0)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        label = ttk.Label(self, text='A new update for ninfs is available!')
        label.grid(row=0, column=0, sticky=tk.EW)

        rel_body_full = releaseinfo['body']
        rel_body = rel_body_full[:rel_body_full.find('------')].replace('\r\n', '\n').strip()

        viewer = OutputViewer(self, output=[rel_body])
        viewer.grid(row=1, column=0, sticky=tk.NSEW)

        self.wizardcontainer.next_button.configure(text='Open release info')
        self.wizardcontainer.set_next_enabled(True)

    def next_pressed(self):
        webbrowser.open(self.releaseinfo['html_url'])


def get_latest_release() -> 'dict':
    url = 'https://api.github.com/repos/ihaveamac/ninfs/releases'
    if not version.is_prerelease:
        url += '/latest'

    print('UPDATE: Requesting', url)
    req = Request(url, headers={'Accept': 'application/vnd.github.v3+json'})
    with urlopen(req) as u:  # type: HTTPResponse
        data = json.load(u)

    if version.is_prerelease:
        data = data[0]

    return data


def thread_update_check(gui: 'NinfsGUI'):
    rel = get_latest_release()
    latest_version: 'Version' = parse_version(rel['tag_name'])

    print('UPDATE: Latest version:', latest_version)
    if latest_version > version:
        wizard_window = WizardContainer(gui)
        wizard_window.change_frame(UpdateNotificationWindow, releaseinfo=rel)
        wizard_window.focus()
