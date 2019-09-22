# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import os

from PySide2.QtWidgets import QComboBox, QLineEdit

from .util import show_dialog


class ComboBoxDND(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        event.accept()
        return super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        event.accept()
        return super().dragMoveEvent(event)

    def dropEvent(self, event):
        event.accept()
        return super().dropEvent(event)


class LineEditDND(QLineEdit):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if len(event.mimeData().urls()) == 1:
            event.accept()

    def dragMoveEvent(self, event):
        event.accept()
        return super().dragMoveEvent(event)

    def dropEvent(self, event):
        event.accept()
        urls = event.mimeData().urls()
        if len(urls) > 1:
            show_dialog('Please only drag and drop one file at a time.')
            return

        path = urls[0].toLocalFile() if os.name != 'nt' else urls[0].toLocalFile().replace('/', '\\')
        self.setText(path)
