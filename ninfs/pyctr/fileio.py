from io import BufferedIOBase
from threading import Lock
from weakref import WeakValueDictionary
from typing import TYPE_CHECKING

from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter

from .common import _raise_if_closed

if TYPE_CHECKING:
    from typing import BinaryIO

# this prevents two SubsectionIO instances on the same file object from interfering with eachother
_lock_objects = WeakValueDictionary()


class SubsectionIO(BufferedIOBase):
    """Provides read-write access to a subsection of a file."""

    closed = False
    _seek = 0

    def __init__(self, file: 'BinaryIO', offset: int, size: int):
        # get existing Lock object for file, or create a new one
        file_id = id(file)
        try:
            self._lock = _lock_objects[file_id]
        except KeyError:
            self._lock = Lock()
            _lock_objects[file_id] = self._lock

        self._reader = file
        self._offset = offset
        self._size = size
        # subsection end is stored for convenience
        self._end = offset + size

    def __repr__(self):
        return f'{type(self).__name__}(file={self._reader!r}, offset={self._offset!r}, size={self._size!r})'

    def close(self):
        self.closed = True
        # remove Lock reference, so it can be automatically removed from the WeakValueDictionary once all SubsectionIO
        #   instances for the base file are closed
        self._lock = None

    __del__ = close

    @_raise_if_closed
    def read(self, size: int = -1) -> bytes:
        if size == -1:
            size = self._size - self._seek
        if self._offset + self._seek > self._end:
            # if attempting to read after the section, return nothing
            return b''
        if self._seek + size > self._size:
            size = self._size - self._seek
           
        with self._lock:
            self._reader.seek(self._seek + self._offset)
            data = self._reader.read(size)

        self._seek += len(data)
        return data

    @_raise_if_closed
    def seek(self, seek: int, whence: int = 0) -> int:
        if whence == 0:
            if seek < 0:
                raise ValueError(f'negative seek value {seek}')
            self._seek = min(seek, self._size)
        elif whence == 1:
            self._seek = max(self._seek + seek, 0)
        elif whence == 2:
            self._seek = max(self._size + seek, 0)
        else:
            if not isinstance(whence, int):
                raise TypeError(f'an integer is required (got type {type(whence).__name__}')
            raise ValueError(f'invalid whence ({seek}, should be 0, 1 or 2)')
        return self._seek

    @_raise_if_closed
    def write(self, data: bytes) -> int:
        if self._seek > self._size:
            # attempting to write past subsection
            return 0
        data_len = len(data)
        data_end = data_len + self._seek
        if data_end > self._size:
            data = data[:-(data_end - self._size)]

        with self._lock:
            self._reader.seek(self._seek + self._offset)
            data_written = self._reader.write(data)

        self._seek += data_written
        return data_written

    @_raise_if_closed
    def readable(self) -> bool:
        return self._reader.readable()

    @_raise_if_closed
    def writable(self) -> bool:
        return self._reader.writable()

    @_raise_if_closed
    def seekable(self) -> bool:
        return self._reader.seekable()


class _CryptoFileBase(BufferedIOBase):
    """Base class for CTR and CBC IO classes."""

    closed = False
    _reader: 'BinaryIO'

    def __repr__(self):
        return f'{type(self).__name__}(file={self._reader!r}, key={self._key!r}, counter={self._counter!r})'

    def close(self):
        self.closed = True

    __del__ = close

    @_raise_if_closed
    def flush(self):
        self._reader.flush()

    @_raise_if_closed
    def tell(self) -> int:
        return self._reader.tell()

    @_raise_if_closed
    def readable(self) -> bool:
        return self._reader.readable()

    @_raise_if_closed
    def writable(self) -> bool:
        return self._reader.writable()

    @_raise_if_closed
    def seekable(self) -> bool:
        return self._reader.seekable()


class CTRFileIO(_CryptoFileBase):
    """Provides transparent read-write AES-CTR encryption as a file-like object."""

    def __init__(self, file: 'BinaryIO', key: bytes, counter: int):
        self._reader = file
        self._key = key
        self._counter = counter

    @_raise_if_closed
    def read(self, size: int = -1) -> bytes:
        cur_offset = self.tell()
        data = self._reader.read(size)
        counter = self._counter + (cur_offset >> 4)
        cipher = AES.new(self._key, AES.MODE_CTR, counter=Counter.new(128, initial_value=counter))
        # beginning padding
        cipher.decrypt(b'\0' * (cur_offset % 0x10))
        return cipher.decrypt(data)

    read1 = read  # probably make this act like read1 should, but this for now enables some other things to work

    @_raise_if_closed
    def write(self, data: bytes) -> int:
        cur_offset = self.tell()
        counter = self._counter + (cur_offset >> 4)
        print(self._key, counter)
        cipher = AES.new(self._key, AES.MODE_CTR, counter=Counter.new(128, initial_value=counter))
        # beginning padding
        cipher.encrypt(b'\0' * (cur_offset % 10))
        return self._reader.write(cipher.encrypt(data))

    @_raise_if_closed
    def seek(self, seek: int, whence: int = 0) -> int:
        # TODO: if the seek goes past the file, the data between the former EOF and seek point should also be encrypted.
        return self._reader.seek(seek, whence)


class CBCFileIO(_CryptoFileBase):
    """Provides transparent read-only AES-CBC encryption as a file-like object."""

    def __init__(self, file: 'BinaryIO', key: bytes, iv: bytes):
        self._reader = file
        self._key = key
        self._iv = iv

    @_raise_if_closed
    def read(self, size: int = -1):
        offset = self.tell()

        # if encrypted, the block needs to be decrypted first
        # CBC requires a full block (0x10 in this case). and the previous
        #   block is used as the IV. so that's quite a bit to read if the
        #   application requires just a few bytes.
        # thanks Stary2001 for help with random-access crypto

        before = offset % 16
        if offset - before == 0:
            iv = self._iv
        else:
            # seek back one block to read it as iv
            self._reader.seek(-0x10 - before, 1)
            iv = self._reader.read(0x10)
        # this is done since we may not know the original size of the file
        # and the caller may have requested -1 to read all the remaining data
        data_before = self._reader.read(before)
        data_requested = self._reader.read(size)
        data_requested_len = len(data_requested)
        data_total_len = len(data_before) + data_requested_len
        if data_total_len % 16:
            data_after = self._reader.read(16 - (data_total_len % 16))
            self._reader.seek(-len(data_after), 1)
        else:
            data_after = b''
        cipher = AES.new(self._key, AES.MODE_CBC, iv)
        # decrypt data, and cut off extra bytes
        return cipher.decrypt(
            b''.join((data_before, data_requested, data_after))
        )[before:data_requested_len + before]

    read1 = read  # probably make this act like read1 should, but this for now enables some other things to work

    @_raise_if_closed
    def seek(self, seek: int, whence: int = 0):
        # even though read re-seeks to read required data, this allows the underlying object to handle seek how it wants
        return self._reader.seek(seek, whence)

    @_raise_if_closed
    def writable(self) -> bool:
        return False
