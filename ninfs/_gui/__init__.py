# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

# This will be something some day!

import os
import sys

from PySide2.QtWidgets import QApplication, QLabel, QMainWindow, QWidget, QVBoxLayout
from PySide2.QtGui import QIcon


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # set application icon
        if os.name == 'nt':
            self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'data', 'windows.ico')))

        # create initial widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        # set window's main widget
        self.setCentralWidget(main_widget)
        main_widget.setLayout(main_layout)

        temp_label = QLabel('This exists, just so the project will build and run. This will be something some day!')
        main_layout.addWidget(temp_label)


def main(_pyi=False, _allow_admin=False):
    app = QApplication()
    if os.name == 'nt':
        # use Fusion style on Windows
        app.setStyle('Fusion')
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())
