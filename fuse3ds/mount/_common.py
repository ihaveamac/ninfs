# This file is a part of fuse-3ds.
#
# Copyright (c) 2017-2018 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import logging
from argparse import ArgumentParser, SUPPRESS
from errno import EROFS
from functools import wraps
from io import BufferedIOBase
from sys import exit, platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Generator, Tuple, Union

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

dev_argp = ArgumentParser(add_help=False)
dev_argp.add_argument('--dev', help='use dev keys', action='store_const', const=1, default=0)

seeddb_argp = ArgumentParser(add_help=False)
seeddb_argp.add_argument('--seeddb', help='path to seeddb.bin')


def main_args(name: str, help: str) -> ArgumentParser:
    parser = ArgumentParser(add_help=False)
    parser.add_argument(name, help=help)
    parser.add_argument('mount_point', help='mount point')
    return parser


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
    def seekable(self) -> bool:
        return True
