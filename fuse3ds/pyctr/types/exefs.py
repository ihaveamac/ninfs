# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from typing import TYPE_CHECKING, NamedTuple

from ..common import PyCTRError
from ..util import readle

if TYPE_CHECKING:
    from typing import BinaryIO, Dict, Iterable

__all__ = ['EMPTY_ENTRY', 'ExeFSError', 'InvalidExeFSError', 'CodeDecompressionError', 'decompress_code', 'ExeFSEntry',
           'ExeFSReader']

EMPTY_ENTRY = b'\0' * 0x10


class ExeFSError(PyCTRError):
    """Generic exception for ExeFS operations."""


class InvalidExeFSError(ExeFSError):
    """Invalid ExeFS header."""


class CodeDecompressionError(ExeFSError):
    """Exception when attempting to decompress ExeFS .code."""


# lazy check
CODE_MAX_SIZE = 0x2300000


def decompress_code(code: bytes) -> bytes:
    # remade from C code, this could probably be done better
    # https://github.com/d0k3/GodMode9/blob/689f6f7cf4280bf15885cbbf848d8dce81def36b/arm9/source/game/codelzss.c#L25-L93
    off_size_comp = int.from_bytes(code[-8:-4], 'little')
    add_size = int.from_bytes(code[-4:], 'little')
    comp_start = 0
    code_len = len(code)

    code_comp_size = off_size_comp & 0xFFFFFF
    code_comp_end = code_comp_size - ((off_size_comp >> 24) % 0xFF)
    code_dec_size = code_len + add_size

    if code_len < 8:
        raise CodeDecompressionError('code_len < 8')
    if code_len > CODE_MAX_SIZE:
        raise CodeDecompressionError('code_len > CODE_MAX_SIZE')

    if code_comp_size <= code_len:
        comp_start = code_len - code_comp_size

    if code_comp_end < 0:
        raise CodeDecompressionError('code_comp_end < 0')
    if code_dec_size > CODE_MAX_SIZE:
        raise CodeDecompressionError('code_dec_size > CODE_MAX_SIZE')

    dec = bytearray(code)
    dec.extend(b'\0' * add_size)

    data_end = comp_start + code_dec_size
    ptr_in = comp_start + code_comp_end
    ptr_out = code_dec_size

    while ptr_in > comp_start and ptr_out > comp_start:
        if ptr_out < ptr_in:
            raise CodeDecompressionError('ptr_out < ptr_in')

        ptr_in -= 1
        ctrl_byte = dec[ptr_in]
        for i in range(7, -1, -1):
            if ptr_in <= comp_start or ptr_out <= comp_start:
                break

            if (ctrl_byte >> i) & 1:
                ptr_in -= 2
                seg_code = int.from_bytes(dec[ptr_in:ptr_in + 2], 'little')
                if ptr_in < comp_start:
                    raise CodeDecompressionError('ptr_in < comp_start')
                seg_off = (seg_code & 0x0FFF) + 2
                seg_len = ((seg_code >> 12) & 0xF) + 3

                if ptr_out - seg_len < comp_start:
                    raise CodeDecompressionError('ptr_out - seg_len < comp_start')
                if ptr_out + seg_off >= data_end:
                    raise CodeDecompressionError('ptr_out + seg_off >= data_end')

                c = 0
                while c < seg_len:
                    byte = dec[ptr_out + seg_off]
                    ptr_out -= 1
                    dec[ptr_out] = byte
                    c += 1
            else:
                if ptr_out == comp_start:
                    raise CodeDecompressionError('ptr_out == comp_start')
                if ptr_in == comp_start:
                    raise CodeDecompressionError('ptr_in == comp_start')

                ptr_out -= 1
                ptr_in -= 1
                dec[ptr_out] = dec[ptr_in]

    if ptr_in != comp_start:
        raise CodeDecompressionError('ptr_in != comp_start')
    if ptr_out != comp_start:
        raise CodeDecompressionError('ptr_out != comp_start')

    return bytes(dec)


class ExeFSEntry(NamedTuple):
    name: str
    offset: int
    size: int
    hash: bytes


class ExeFSReader:
    """
    Class for 3DS ExeFS.

    http://3dbrew.org/wiki/ExeFS
    """

    def __init__(self, entries: 'Iterable[ExeFSEntry]', strict: bool = False):
        self.entries: Dict[str, ExeFSEntry] = {}
        for x in entries:
            if x.offset % 0x200:
                msg = f'{x.name} has an offset not aligned to 0x200 ({x.offset:#x})'
                if strict:
                    raise InvalidExeFSError(msg)
                print(f'Warning: {msg}.\n'
                      f'This ExeFS will not work on console.')
            for e in self.entries.values():
                if e.offset + e.size > x.offset > e.offset:
                    msg = f'{x.name} overlaps with {e.name}'
                    if strict:
                        raise InvalidExeFSError(msg)
                    print('Warning:', msg)
            self.entries[x.name] = x

    def __hash__(self) -> int:
        return hash(self.entries.values())

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, item: str) -> ExeFSEntry:
        return self.entries[item]

    @classmethod
    def load(cls, fp: 'BinaryIO', strict: bool = False) -> 'ExeFSReader':
        """Load an ExeFS from a file-like object."""
        header = fp.read(0x200)
        if len(set(header)) == 1:
            raise InvalidExeFSError('Empty header')

        entries = []
        # exefs entry number, exefs hash number
        try:
            for en, hn in zip(range(0, 0xA0, 0x10), range(0x1E0, 0xA0, -0x20)):
                entry_raw = header[en:en + 0x10]
                entry_hash = header[hn:hn + 0x20]
                if entry_raw == EMPTY_ENTRY:
                    continue
                entries.append(ExeFSEntry(name=entry_raw[0:8].rstrip(b'\0').decode('ascii'),
                                          offset=readle(entry_raw[8:12]),
                                          size=readle(entry_raw[12:16]),
                                          hash=entry_hash))
        except UnicodeDecodeError:
            raise InvalidExeFSError('Failed to convert name, probably not a valid ExeFS')

        return cls(entries, strict)

    @classmethod
    def from_file(cls, fn: str, strict: bool = False) -> 'ExeFSReader':
        with open(fn, 'rb') as f:
            return cls.load(f, strict)
