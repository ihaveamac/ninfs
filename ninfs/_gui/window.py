# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import os

from PySide2.QtWidgets import QLabel, QMainWindow, QWidget, QVBoxLayout
from PySide2.QtGui import QIcon

from .util import windows
if windows:
    from .util import get_unused_drives

mount_types = {
    'cci': 'CTR Cart Image (".3ds", ".cci")',
    'cdn': 'CDN contents ("cetk", "tmd", and contents)',
    'cia': 'CTR Importable Archive (".cia")',
    'exefs': 'Executable Filesystem (".exefs", "exefs.bin")',
    'nandctr': 'Nintendo 3DS NAND backup ("nand.bin")',
    'nandhac': 'Nintendo Switch NAND backup ("rawnand.bin")',
    'nandtwl': 'Nintendo DSi NAND backup ("nand_dsi.bin")',
    'ncch': 'NCCH (".cxi", ".cfa", ".ncch", ".app")',
    'romfs': 'Read-only Filesystem (".romfs", "romfs.bin")',
    'sd': 'SD Card Contents ("Nintendo 3DS" from SD)',
    'srl': 'Nintendo DS ROM image (".nds", ".srl")',
    'threedsx': '3DSX Homebrew (".3dsx")',
}

type_exts = {
    'cci': 'CTR Cart Image (*.3ds *.cci *.csu)',
    'cdn': '',  # maybe tmd will go here, but it needs to be implemented first
    'cia': 'CTR Importable Archive (*.cia)',
    'exefs': 'Executable Filesystem (*.exefs exefs.bin)',
    'nandctr': 'Nintendo 3DS NAND backup (*.bin)',
    'nandhac': 'Nintendo Switch NAND backup (*.bin)',
    'nandtwl': 'Nintendo DSi NAND backup (*.bin)',
    'ncch': 'NCCH (*.cxi *.cfa *.ncch *.app)',
    'romfs': 'Read-only Filesystem (*.romfs romfs.bin)',
    'sd': '',  # not a file
    'srl': 'Nintendo DS ROM image (*.nds *.srl)',
    'threedsx': '3DSX Homebrew (*.3dsx)',
}

ctr_types = ('cci', 'cdn', 'cia', 'exefs', 'nandctr', 'ncch', 'romfs', 'sd', 'threedsx')
twl_types = ('nandtwl', 'srl')
hac_types = ('nandhac',)

uses_directory = ('cdn', 'sd')


class MainWindow(QMainWindow):
    """Main window for ninfs."""
    current_type: str = None

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
