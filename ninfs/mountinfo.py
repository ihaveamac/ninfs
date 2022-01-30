# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

types = {
    'cci': {
        'name': 'CTR Cart Image',
        'info': '".3ds", ".cci"'
    },
    'cdn': {
        'name': 'CDN contents',
        'info': '"cetk", "tmd", and contents'
    },
    'cia': {
        'name': 'CTR Importable Archive',
        'info': '".cia"'
    },
    'exefs': {
        'name': 'Executable Filesystem',
        'info': '".exefs", "exefs.bin"'
    },
    'nandctr': {
        'name': 'Nintendo 3DS NAND backup',
        'info': '"nand.bin"'
    },
    'nandtwl': {
        'name': 'Nintendo DSi NAND backup',
        'info': '"nand_dsi.bin"'
    },
    'nandhac': {
        'name': 'Nintendo Switch NAND backup',
        'info': '"rawnand.bin"'
    },
    'nandbb': {
        'name': 'iQue Player NAND backup',
        'info': '"nand.bin"'
    },
    'ncch': {
        'name': 'NCCH',
        'info': '".cxi", ".cfa", ".ncch", ".app"'
    },
    'romfs': {
        'name': 'Read-only Filesystem',
        'info': '".romfs", "romfs.bin"'
    },
    'sd': {
        'name': 'SD Card Contents',
        'info': '"Nintendo 3DS" from SD'
    },
    'sdtitle': {
        'name': 'Installed SD Title Contents',
        'info': '"*.tmd" and "*.app" files'
    },
    'srl': {
        'name': 'Nintendo DS ROM image',
        'info': '".nds", ".srl"'
    },
    'threedsx': {
        'name': '3DSX Homebrew',
        'info': '".3dsx"'
    },
}

aliases = {
    '3ds': 'cci',
    '3dsx': 'threedsx',
    'app': 'ncch',
    'csu': 'cci',
    'cxi': 'ncch',
    'cfa': 'ncch',
    'nand': 'nandctr',
    'nanddsi': 'nandtwl',
    'nandique': 'nandbb',
    'nandswitch': 'nandhac',
    'nandnx': 'nandhac',
    'nds': 'srl',
}

categories = {
    'Nintendo 3DS': ['cci', 'cdn', 'cia', 'exefs', 'nandctr', 'ncch', 'romfs', 'sd', 'sdtitle', 'threedsx'],
    'Nintendo DS / DSi': ['nandtwl', 'srl'],
    'Nintendo Switch': ['nandhac'],
    'iQue Player': ['nandbb']
}

# this will add the "Use developer-unit keys" option to Advanced options in the gui
supports_dev_keys = ['cci', 'cdn', 'cia', 'nandctr', 'ncch', 'sd', 'sdtitle']


def get_type_info(mount_type):
    return types[aliases.get(mount_type, mount_type)]
