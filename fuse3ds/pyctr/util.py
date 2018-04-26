import os
from math import ceil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Tuple

__all__ = ['readle', 'readbe', 'roundup', 'config_dirs']


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
config_dirs: 'Tuple[str, str]' = (os.path.join(_home, '3ds'), os.path.join(_home, '.3ds'))
