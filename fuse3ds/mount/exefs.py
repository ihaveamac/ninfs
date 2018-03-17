#!/usr/bin/env python3

"""
Mounts Executable Filesystem (ExeFS) files, creating a virtual filesystem of the ExeFS contents.
"""

import argparse
import errno
import hashlib
import logging
import os
import stat
import sys
from typing import BinaryIO

from pyctr.exefs import ExeFSReader, ExeFSEntry, CodeDecompressionError, decompress_code as _decompress_code

from . import _common

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ModuleNotFoundError:
    sys.exit("fuse module not found, please install fusepy to mount images "
             "(`{} install https://github.com/billziss-gh/fusepy/archive/windows.zip`).".format(_common.pip_command))
except Exception as e:
    sys.exit("Failed to import the fuse module:\n"
             "{}: {}".format(type(e).__name__, e))


class ExeFSMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, exefs_fp: BinaryIO, g_stat: os.stat_result, decompress_code=False):
        self.g_stat = {'st_ctime': int(g_stat.st_ctime), 'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        self.f = exefs_fp

        self.exefs_reader = ExeFSReader.load(exefs_fp)
        self.files = {'/' + x.name.replace('.', '', 1) + '.bin': x for x in self.exefs_reader.entries.values()}
        self.exefs_size = sum(x.size for x in self.exefs_reader.entries.values())

        if decompress_code and '/code.bin' in self.files:
            print('ExeFS: Decompressing .code...', end='', flush=True)
            try:
                item = self.files['/code.bin']
                with open('/Volumes/ThingsMore/nintendo/3DS/fuse-3ds/CODE.bin', 'wb') as f:
                    f.write(self.read('/code.bin', item.size, item.offset, 0))
                self.code_dec = _decompress_code(self.read('/code.bin', item.size, item.offset, 0))
                self.files['/code-dec.bin'] = ExeFSEntry(name='code-dec', offset=-1, size=len(self.code_dec),
                                                         hash=hashlib.sha256(self.code_dec).digest())
                print(' done!')
            except CodeDecompressionError as e:
                print('\nFailed to decompress .code: {}: {}'.format(type(e).__name__, e))

    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        if path == '/':
            st = {'st_mode': (stat.S_IFDIR | 0o555), 'st_nlink': 2}
        else:
            try:
                item = self.files[path]
            except KeyError:
                raise FuseOSError(errno.ENOENT)
            st = {'st_mode': (stat.S_IFREG | 0o444), 'st_size': item.size, 'st_nlink': 1}
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        yield from ('.', '..')
        yield from (x[1:] for x in self.files)

    def read(self, path, size, offset, fh):  # TODO: this
        try:
            item = self.files[path]
        except KeyError:
            raise FuseOSError(errno.ENOENT)
        if item.offset == -1:
            # special case for code-dec
            return self.code_dec[offset:offset + size]

        real_offset = 0x200 + item.offset + offset
        if real_offset > item.offset + item.size:
            return b''
        if offset + size > item.size:
            size = item.size - offset
        self.f.seek(real_offset)
        return self.f.read(size)

    def statfs(self, path):
        return {'f_bsize': 4096, 'f_blocks': self.exefs_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.exefs_reader)}


def main():
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS Executable Filesystem (ExeFS) files.',
                                     parents=(_common.default_argp,
                                              _common.main_positional_args('exefs', 'ExeFS file')))
    parser.add_argument('--decompress-code', help='decompress the .code section', action='store_true')

    a = parser.parse_args()
    opts = dict(_common.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    exefs_stat = os.stat(a.exefs)

    with open(a.exefs, 'rb') as f:
        mount = ExeFSMount(exefs_fp=f, g_stat=exefs_stat, decompress_code=a.decompress_code)
        if _common.macos or _common.windows:
            opts['fstypename'] = 'ExeFS'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            path_to_show = os.path.realpath(a.exefs).rsplit('/', maxsplit=2)
            if _common.macos:
                opts['volname'] = "Nintendo 3DS ExeFS ({}/{})".format(path_to_show[-2], path_to_show[-1])
            elif _common.windows:
                # volume label can only be up to 32 chars
                # TODO: maybe I should show the path here, if i can shorten it properly
                opts['volname'] = "Nintendo 3DS ExeFS"
        fuse = FUSE(mount, a.mount_point, foreground=a.fg or a.do, ro=True, nothreads=True,
                    fsname=os.path.realpath(a.exefs).replace(',', '_'), **opts)


if __name__ == '__main__':
    main()
