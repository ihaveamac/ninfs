import inspect
import sys
from argparse import ArgumentParser, SUPPRESS
from typing import Generator, Tuple, Union

from fuse import Operations

windows = sys.platform in {'win32', 'cygwin'}
macos = sys.platform == 'darwin'

python_cmd = 'py -3' if windows else 'python3'

# this is a temporary (hopefully) thing to check for the fusepy version on windows, since a newer commit on
# a fork of it is currently required for windows.
# I know this is a bad idea but I just don't want users complaining about it not working properly with their
# existing fusepy installs. I hope I can remove this when the windows support is merged into upstream.
if windows:
    from fuse import fuse_file_info
    import ctypes
    # noinspection PyProtectedMember
    if fuse_file_info._fields_[1][1] is not ctypes.c_int:  # checking fh_old type which is different for windows
        sys.exit('Please update fusepy to use fuse-3ds. More information can be found at:\n'
                 '  https://github.com/ihaveamac/fuse-3ds')
    del fuse_file_info, ctypes

default_argp = ArgumentParser(add_help=False)
default_argp.add_argument('-f', '--fg', help='run in foreground', action='store_true')
default_argp.add_argument('-d', help='debug output (fuse/winfsp log)', action='store_true')
default_argp.add_argument('--do', help=SUPPRESS, action='store_true')  # debugging using python logging
default_argp.add_argument('-o', metavar='OPTIONS', help='mount options')

readonly_argp = ArgumentParser(add_help=False)
readonly_argp.add_argument('-r', '--ro', help='mount read-only', action='store_true')

dev_argp = ArgumentParser(add_help=False)
dev_argp.add_argument('--dev', help="use dev keys", action='store_const', const=1, default=0)

seeddb_argp = ArgumentParser(add_help=False)
seeddb_argp.add_argument('--seeddb', help="path to seeddb.bin")

def main_positional_args(name: str, help: str) -> ArgumentParser:
    parser = ArgumentParser(add_help=False)
    parser.add_argument(name, help=help)
    parser.add_argument('mount_point', help='mount point')
    return parser


# aren't type hints great?
def parse_fuse_opts(opts) -> Generator[Tuple[str, Union[str, bool]], None, None]:
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


def raise_if_closed(func):
    def decorator(self, *args, **kwargs):
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        return func(self, *args, **kwargs)
    decorator.__signature__ = inspect.signature(func)
    decorator.__annotations__ = func.__annotations__
    decorator.__name__ = func.__name__
    decorator.__doc__ = func.__doc__
    return decorator

class VirtualFileWrapper:
    """Wrapper for a FUSE Operations class for things that need a file-like object."""

    closed = False
    _seek = 0

    def __init__(self, fuse_op: Operations, path: str, size: int):
        self.fuse_op = fuse_op
        self.path = path
        self.size = size

    @raise_if_closed
    def read(self, size: int = -1) -> bytes:
        if size == -1:
            size = self.size - self._seek
        data = self.fuse_op.read(self.path, size, self._seek, 0)
        self._seek += len(data)
        return data

    @raise_if_closed
    def seek(self, seek: int, whence: int = 0) -> int:
        if whence == 0:
            if seek < 0:
                raise ValueError("negative seek value -1")
            self._seek = min(seek, self.size)
        elif whence == 1:
            self._seek = max(self._seek + seek, 0)
        elif whence == 2:
            self._seek = max(self.size + seek, 0)
        return self._seek

    @raise_if_closed
    def tell(self) -> int:
        return self._seek

    def close(self):
        self.closed = True

    @raise_if_closed
    def readable(self) -> bool:
        return True

    @raise_if_closed
    def writable(self) -> bool:
        return False

    @raise_if_closed
    def seekable(self) -> bool:
        return True
