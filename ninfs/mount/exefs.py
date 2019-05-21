# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts Executable Filesystem (ExeFS) files, creating a virtual filesystem of the ExeFS contents.
"""

import logging
import os
from errno import ENOENT
from hashlib import sha256
from stat import S_IFDIR, S_IFREG
from sys import argv
from typing import TYPE_CHECKING

from pyctr.types.exefs import ExeFSReader, ExeFSEntry, decompress_code as _decompress_code
from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context

if TYPE_CHECKING:
    from typing import BinaryIO, Dict


class ExeFSMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, exefs_fp: 'BinaryIO', g_stat: os.stat_result, decompress_code: bool = False, strict: bool = False):
        self.g_stat = {'st_ctime': int(g_stat.st_ctime), 'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        self.reader = ExeFSReader.load(exefs_fp, strict)
        self.files: Dict[str, ExeFSEntry] = {'/' + x.name.replace('.', '', 1) + '.bin': x
                                             for x in self.reader.entries.values()}
        self.exefs_size = sum(x.size for x in self.reader.entries.values())
        self.code_dec = b''
        self.decompress_code = decompress_code

        self.f = exefs_fp

    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass

    destroy = __del__

    # TODO: maybe do this in a way that allows for multiprocessing (titledir)
    def init(self, path, data=None):
        try:
            item = self.files['/code.bin']
        except KeyError:
            return  # no code, don't attempt to decompress
        else:
            if self.decompress_code:
                print('ExeFS: Decompressing .code...')
                # noinspection PyBroadException
                try:
                    self.code_dec = _decompress_code(data if data else self.read('/code.bin', item.size, item.offset, 0))
                    self.files['/code-decompressed.bin'] = ExeFSEntry(name='code-decompressed', offset=-1,
                                                                      size=len(self.code_dec),
                                                                      hash=sha256(self.code_dec).digest())
                    print('ExeFS: Done!')
                except Exception as e:
                    print(f'ExeFS: Failed to decompress .code: {type(e).__name__}: {e}')
            else:
                print('ExeFS: .code aleady decompressed')
                self.files['/code-decompressed.bin'] = ExeFSEntry(name='code-decompressed', offset=item.offset,
                                                                  size=item.size, hash=item.hash)

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        if path == '/':
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        else:
            try:
                item = self.files[path]
            except KeyError:
                raise FuseOSError(ENOENT)
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': item.size, 'st_nlink': 1}
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    @_c.ensure_lower_path
    def readdir(self, path, fh):
        yield from ('.', '..')
        yield from (x[1:] for x in self.files)

    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        try:
            item = self.files[path]
        except KeyError:
            raise FuseOSError(ENOENT)
        if item.offset == -1:
            # special case for code-decompressed
            return self.code_dec[offset:offset + size]

        real_offset = 0x200 + item.offset + offset
        if real_offset > item.offset + item.size + 0x200:
            return b''
        if offset + size > item.size:
            size = item.size - offset
        self.f.seek(real_offset)
        return self.f.read(size)

    @_c.ensure_lower_path
    def statfs(self, path):
        return {'f_bsize': 4096, 'f_blocks': self.exefs_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.reader)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS Executable Filesystem (ExeFS) files.',
                            parents=(_c.default_argp, _c.main_args('exefs', 'ExeFS file')))
    parser.add_argument('--decompress-code', help='decompress the .code section', action='store_true')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    exefs_stat = os.stat(a.exefs)

    with open(a.exefs, 'rb') as f:
        mount = ExeFSMount(exefs_fp=f, g_stat=exefs_stat, decompress_code=a.decompress_code)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'ExeFS'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            path_to_show = os.path.realpath(a.exefs).rsplit('/', maxsplit=2)
            if _c.macos:
                opts['volname'] = f'Nintendo 3DS ExeFS ({path_to_show[-2]}/{path_to_show[-1]})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = 'Nintendo 3DS ExeFS'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=os.path.realpath(a.exefs).replace(',', '_'), **opts)
