# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from configparser import ConfigParser
from os import environ, makedirs
from os.path import expanduser, isdir, join
from sys import platform
from threading import Lock

__all__ = ['get_bool', 'set_bool']

CONFIG_FILENAME = 'config.ini'

home = expanduser('~')

lock = Lock()

if platform == 'win32':
    config_dir = join(environ['APPDATA'], 'ninfs')
elif platform == 'darwin':
    config_dir = join(home, 'Library', 'Application Support', 'ninfs')
else:
    # probably linux or bsd or something
    # if by some chance an OS uses different paths, feel free to let me know or make a PR
    config_root = environ.get('XDG_CONFIG_HOME')
    if not config_root:
        # check other paths in XDG_CONFIG_DIRS to see if ninfs already exists in one of them
        config_roots = environ.get('XDG_CONFIG_DIRS')
        if not config_roots:
            config_roots = '/etc/xdg'
        config_paths = config_roots.split(':')
        for path in config_paths:
            d = join(path, 'ninfs')
            if isdir(d):
                config_root = d
                break
    # check again to see if it was set
    if not config_root:
        config_root = join(home, '.config')
    config_dir = join(config_root, 'ninfs')

makedirs(config_dir, exist_ok=True)

config_file = join(config_dir, CONFIG_FILENAME)

parser = ConfigParser()

# defaults
parser['update'] = {}
parser['update']['onlinecheck'] = 'false'
parser['internal'] = {}
parser['internal']['askedonlinecheck'] = 'false'


def save_config():
    with lock:
        print('Saving to:', config_file)
        with open(config_file, 'w') as f:
            parser.write(f)


def get_bool(section: 'str', key: 'str'):
    return parser.getboolean(section, key)


def set_bool(section: 'str', key: 'str', value: bool):
    parser.set(section, key, 'true' if value else 'false')
    save_config()


# load user config if possible
loaded = parser.read(config_file)
if not loaded:
    save_config()
