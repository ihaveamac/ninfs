# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from sys import platform
from typing import TYPE_CHECKING

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from typing import Dict, List

    from PySide2.QtWidgets import QMainWindow

windows = platform == 'win32'

# to be set in the main function
main_window: 'QMainWindow'

if windows:
    from string import ascii_uppercase
    from ctypes import windll

    def get_unused_drives():
        """Get a list of unused drive letters."""
        # https://stackoverflow.com/questions/827371/is-there-a-way-to-list-all-the-available-drive-letters-in-python
        drives: 'List[str]' = []
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in ascii_uppercase:
            if not bitmask & 1:
                drives.append(letter)
            bitmask >>= 1

        return drives


def show_dialog(text: str, infotext: str = None, icon=QMessageBox.Information):
    msg_box = QMessageBox(main_window)
    msg_box.setWindowModality(Qt.WindowModal)
    msg_box.setWindowTitle('ninfs')
    msg_box.setIcon(icon)
    msg_box.setText(text)
    if infotext:
        msg_box.setInformativeText(infotext)
    msg_box.open()
