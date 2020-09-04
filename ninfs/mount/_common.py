# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import logging
import time
from argparse import ArgumentParser, SUPPRESS
from errno import EROFS
from functools import wraps
from io import BufferedIOBase
from os import stat, stat_result
from os.path import realpath as real_realpath
from sys import exit, platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from os import PathLike
    from typing import BinaryIO, Generator, Tuple, Union
    # this is a lazy way to make type checkers stop complaining
    BufferedIOBase = BinaryIO

windows = platform in {'win32', 'cygwin'}
macos = platform == 'darwin'

python_cmd = 'py -3' if windows else 'python3'

# TODO: switch to use_ns in all scripts
# noinspection PyBroadException
try:
    from fuse import FUSE, FuseOSError, Operations, fuse_get_context
except Exception as e:
    exit(f'Failed to import the fuse module:\n'
         f'{type(e).__name__}: {e}')


def realpath(path):
    try:
        return real_realpath(path)
    except OSError:
        # can happen on Windows when using it on files inside a WinFsp mount
        pass
    return path


def get_time(path: 'Union[str, PathLike, stat_result]'):
    try:
        if not isinstance(path, stat_result):
            res = stat(path)
        else:
            res = path
        return {'st_ctime': int(res.st_ctime), 'st_mtime': int(res.st_mtime), 'st_atime': int(res.st_atime)}
    except OSError:
        # sometimes os.stat can't be used with a path, such as Windows physical drives
        #   so we need to fake the result
        now = int(time.time())
        return {'st_ctime': now, 'st_mtime': now, 'st_atime': now}


# custom LoggingMixIn modified from the original fusepy, to suppress certain entries.
class LoggingMixIn:
    log = logging.getLogger('fuse.log-mixin')

    def __call__(self, op, path, *args):
        if op != 'access':
            self.log.debug('-> %s %s %s', op, path, repr(args))
        ret = '[Unhandled Exception]'
        try:
            ret = getattr(self, op)(path, *args)
            return ret
        except OSError as e:
            ret = str(e)
            raise
        finally:
            if op != 'access':
                self.log.debug('<- %s %s', op, repr(ret))


default_argp = ArgumentParser(add_help=False)
default_argp.add_argument('-f', '--fg', help='run in foreground', action='store_true')
default_argp.add_argument('-d', help='debug output (fuse/winfsp log)', action='store_true')
default_argp.add_argument('--do', help=SUPPRESS, default=None)  # debugging using python logging
default_argp.add_argument('-o', metavar='OPTIONS', help='mount options')

readonly_argp = ArgumentParser(add_help=False)
readonly_argp.add_argument('-r', '--ro', help='mount read-only', action='store_true')

ctrcrypto_argp = ArgumentParser(add_help=False)
ctrcrypto_argp.add_argument('--boot9', help='path to boot9.bin')
ctrcrypto_argp.add_argument('--dev', help='use dev keys', action='store_const', const=1, default=0)

seeddb_argp = ArgumentParser(add_help=False)
seeddb_argp_group = seeddb_argp.add_mutually_exclusive_group()
seeddb_argp_group.add_argument('--seeddb', help='path to seeddb.bin')
seeddb_argp_group.add_argument('--seed', help='seed as hexstring')


def main_args(name: str, help: str) -> ArgumentParser:
    parser = ArgumentParser(add_help=False)
    parser.add_argument(name, help=help)
    parser.add_argument('mount_point', help='mount point')
    return parser


def load_custom_boot9(path: str, dev: bool = False):
    """Load keys from a custom ARM9 bootROM path."""
    if path:
        from pyctr.crypto import CryptoEngine
        # doing this will set up the keys for all future CryptoEngine objects
        CryptoEngine(boot9=path, dev=dev)


# aren't type hints great?
def parse_fuse_opts(opts) -> 'Generator[Tuple[str, Union[str, bool]], None, None]':
    if not opts:
        return
    for arg in opts.split(','):
        if arg:  # leaves out empty ones
            separated = arg.split('=', maxsplit=1)
            yield separated[0], True if len(separated) == 1 else separated[1]


def remove_first_dir(path: str) -> str:
    sep = path.find('/', 1)
    if sep == -1:
        return '/'
    else:
        return path[sep:]


def get_first_dir(path: str) -> str:
    sep = path.find('/', 1)
    if sep == -1:
        return path
    else:
        return path[:sep]


def ensure_lower_path(method):
    @wraps(method)
    def wrapper(self, path, *args, **kwargs):
        return method(self, path.lower(), *args, **kwargs)
    return wrapper


def raise_on_readonly(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        if self.readonly:
            raise FuseOSError(EROFS)
        return method(self, *args, **kwargs)
    return wrapper


def _raise_if_closed(method):
    @wraps(method)
    def decorator(self, *args, **kwargs):
        if self.closed:
            raise ValueError('I/O operation on closed file.')
        return method(self, *args, **kwargs)
    return decorator


class VirtualFileWrapper(BufferedIOBase):
    """Wrapper for a FUSE Operations class for things that need a file-like object."""

    _seek = 0

    # noinspection PyMissingConstructor
    def __init__(self, fuse_op: Operations, path: str, size: int):
        self.fuse_op = fuse_op
        self.path = path
        self.size = size

    @_raise_if_closed
    def read(self, size: int = -1) -> bytes:
        if size == -1:
            size = self.size - self._seek
        data = self.fuse_op.read(self.path, size, self._seek, 0)
        self._seek += len(data)
        return data

    read1 = read  # probably make this act like read1 should, but this for now enables some other things to work

    @_raise_if_closed
    def seek(self, seek: int, whence: int = 0) -> int:
        if whence == 0:
            if seek < 0:
                raise ValueError(f'negative seek value {seek}')
            self._seek = min(seek, self.size)
        elif whence == 1:
            self._seek = max(self._seek + seek, 0)
        elif whence == 2:
            self._seek = max(self.size + seek, 0)
        return self._seek

    @_raise_if_closed
    def tell(self) -> int:
        return self._seek

    @_raise_if_closed
    def readable(self) -> bool:
        return True

    @_raise_if_closed
    def writable(self) -> bool:
        try:
            # types that support writing will have this attribute
            return self.fuse_op.readonly
        except AttributeError:
            return False

    @_raise_if_closed
    def seekable(self) -> bool:
        return True


class SplitFileHandler(BufferedIOBase):
    _fake_seek = 0
    _seek_info = (0, 0)

    def __init__(self, names, mode='rb'):
        self.mode = mode
        self._files = []
        curr_offset = 0
        self._names = tuple(names)
        for idx, f in enumerate(self._names):
            s = stat(f)
            self._files.append((idx, curr_offset, s.st_size))
            curr_offset += s.st_size
        self._total_size = curr_offset

    def _calc_seek(self, pos):
        for idx, info in enumerate(self._files):
            if info[1] <= pos < info[1] + info[2]:
                self._fake_seek = pos
                self._seek_info = (idx, pos - info[1])
                break

    def seek(self, pos, whence=0):
        if whence == 0:
            if pos < 0:
                raise ValueError('negative seek value')
            self._calc_seek(pos)
        elif whence == 1:
            if self._fake_seek - pos < 0:
                pos = 0
            self._calc_seek(self._fake_seek + pos)
        elif whence == 2:
            if self._total_size + pos < 0:
                pos = -self._total_size
            self._calc_seek(self._total_size + pos)
        else:
            if isinstance(whence, int):
                raise ValueError(f'whence value {whence} unsupported')
            else:
                raise TypeError(f'an integer is required (got type {type(whence).__name__})')
        return self._fake_seek

    @_raise_if_closed
    def tell(self):
        return self._fake_seek

    def read(self, count=-1):
        if count == -1:
            count = self._total_size - count
        if self._fake_seek + count > self._total_size:
            count = self._total_size - self._fake_seek

        left = count
        curr = self._seek_info

        full_data = []

        while left:
            info = self._files[curr[0]]
            real_seek = self._fake_seek - info[1]
            to_read = min(info[2] - real_seek, left)

            with open(self._names[curr[0]], 'rb') as f:
                f.seek(real_seek)
                full_data.append(f.read(to_read))

            self._fake_seek += to_read
            try:
                curr = self._files[curr[0] + 1]
                left -= to_read
            except IndexError:
                break  # EOF

        # TODO: make this more efficient
        self._calc_seek(self._fake_seek)

        return b''.join(full_data)

    def write(self, data: bytes):
        left = len(data)
        total = left
        curr = self._seek_info

        while left:
            info = self._files[curr[0]]
            real_seek = self._fake_seek - info[1]
            to_write = min(info[2] - real_seek, left)

            with open(self._names[curr[0]], 'rb+') as f:
                f.seek(real_seek)
                f.write(data[total - left:total - left + to_write])

            self._fake_seek += to_write
            try:
                curr = self._files[curr[0] + 1]
                left -= to_write
            except IndexError:
                break  # EOF

        # TODO: make this more efficient
        self._calc_seek(self._fake_seek)

        return total - left

    @_raise_if_closed
    def readable(self) -> bool:
        return 'r' in self.mode

    def writable(self) -> bool:
        return 'w' in self.mode or 'a' in self.mode

    @_raise_if_closed
    def seekable(self) -> bool:
        return True


class RawDeviceHandler(BufferedIOBase):
    """Handler for easier IO access with raw devices by aligning reads and writes to the sector size."""

    _seek = 0

    def __init__(self, fh: 'BinaryIO', mode: str = 'rb+', sector_size: int = 0x200):
        self._fh = fh
        self.mode = mode
        self._sector_size = sector_size

    @_raise_if_closed
    def seek(self, seek: int, whence: int = 0) -> int:
        if whence == 0:
            if seek < 0:
                raise ValueError(f'negative seek value {seek}')
            self._seek = seek
        elif whence == 1:
            self._seek = max(self._seek + seek, 0)
        elif whence == 2:
            # this doesn't work...
            raise Exception
        return self._seek

    @_raise_if_closed
    def tell(self) -> int:
        return self._seek

    @_raise_if_closed
    def readable(self) -> bool:
        return True

    @_raise_if_closed
    def writable(self) -> bool:
        return True

    @_raise_if_closed
    def seekable(self) -> bool:
        return True
