import os
from math import ceil
from sys import platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List

__all__ = ['windows', 'macos', 'readle', 'readbe', 'roundup', 'config_dirs']

windows = platform in {'win32', 'cygwin'}
macos = platform == 'darwin'


def readle(b: bytes) -> int:
    """Return little-endian bytes to an int."""
    return int.from_bytes(b, 'little')


def readbe(b: bytes) -> int:
    """Return big-endian bytes to an int."""
    return int.from_bytes(b, 'big')


def roundup(offset: int, alignment: int) -> int:
    """Round up a number to a provided alignment."""
    return int(ceil(offset / alignment) * alignment)


_home = os.path.expanduser('~')
config_dirs: 'List[str]' = [os.path.join(_home, '3ds'), os.path.join(_home, '.3ds')]
if windows:
    config_dirs.append(os.path.join(os.environ.get('APPDATA'), '3ds'))
