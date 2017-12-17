import sys

from fuse import Operations


windows = sys.platform in {'win32', 'cygwin'}
macos = sys.platform == 'darwin'


def parse_fuse_opts(opts):
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


class VirtualFileWrapper:
    """Wrapper for a FUSE Operations class for things that need a file-like object."""

    closed = False
    _seek = 0

    def __init__(self, fuse_op: Operations, path: str, size: int):
        self.fuse_op = fuse_op
        self.path = path
        self.size = size

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if size == -1:
            size = self.size - self._seek
        data = self.fuse_op.read(self.path, size, self._seek, 0)
        self._seek += len(data)
        return data

    def seek(self, seek: int, whence: int = 0) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        if whence == 0:
            if seek < 0:
                raise ValueError("negative seek value -1")
            self._seek = min(seek, self.size)
        elif whence == 1:
            self._seek = max(self._seek + seek, 0)
        elif whence == 2:
            self._seek = max(self.size + seek, 0)
        return self._seek

    def tell(self) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        return self._seek

    def close(self):
        self.closed = True

    def readable(self) -> bool:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        return True

    def writable(self) -> bool:
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        return False
