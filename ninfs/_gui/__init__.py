# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import os
import sys

from PySide2.QtWidgets import QApplication

from .window import MainWindow
from . import util


def main(_pyi=False, _allow_admin=False):
    app = QApplication()
    if os.name == 'nt':
        # use Fusion style on Windows
        app.setStyle('Fusion')
    window = MainWindow()
    util.main_window = window
    window.show()

    sys.exit(app.exec_())
