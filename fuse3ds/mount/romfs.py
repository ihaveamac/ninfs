#!/usr/bin/env python3

"""
Mounts Read-only Filesystem (RomFS) files, creating a virtual filesystem of the RomFS contents. Accepts ones with and without an IVFC header (original HANS format).
"""

import logging
import os
from argparse import ArgumentParser
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import exit
from typing import BinaryIO

from pyctr.romfs import RomFSReader, RomFSFileNotFoundError

from . import _common

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ModuleNotFoundError:
    exit("fuse module not found, please install fusepy to mount images "
         "(`{} -mpip install https://github.com/billziss-gh/fusepy/archive/windows.zip`).".format(_common.python_cmd))
except Exception as e:
    exit("Failed to import the fuse module:\n"
         "{}: {}".format(type(e).__name__, e))


class RomFSMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, romfs_fp: BinaryIO, g_stat: os.stat_result):
        # get status change, modify, and file access times
        self.g_stat = {'st_ctime': int(g_stat.st_ctime), 'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        romfs_fp.seek(0, 2)
        self.romfs_size = romfs_fp.tell()
        romfs_fp.seek(0)
        self.reader = RomFSReader.load(romfs_fp, case_insensitive=True)

        self.f = romfs_fp

    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        try:
            item = self.reader.get_info_from_path(path)
        except RomFSFileNotFoundError:
            raise FuseOSError(ENOENT)
        if item.type == 'dir':
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        elif item.type == 'file':
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': item.size, 'st_nlink': 1}
        else:
            # this won't happen unless I fucked up
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        try:
            item = self.reader.get_info_from_path(path)
        except RomFSFileNotFoundError:
            raise FuseOSError(ENOENT)
        yield from ('.', '..')
        yield from item.contents

    def read(self, path, size, offset, fh):
        try:
            item = self.reader.get_info_from_path(path)
        except RomFSFileNotFoundError:
            raise FuseOSError(ENOENT)
        real_offset = item.offset + offset
        if real_offset > item.offset + item.size:
            # do I raise an exception or return nothing? I'm not sure
            return b''
        if offset + size > item.size:
            size = item.size - offset
        self.f.seek(self.reader.data_offset + real_offset)
        return self.f.read(size)

    def statfs(self, path):
        try:
            item = self.reader.get_info_from_path(path)
        except RomFSFileNotFoundError:
            raise FuseOSError(ENOENT)
        return {'f_bsize': 4096, 'f_blocks': self.romfs_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(item.contents)}


def main():
    parser = ArgumentParser(description='Mount Nintendo 3DS Read-only Filesystem (RomFS) files.',
                            parents=(_common.default_argp,
                                              _common.main_positional_args('romfs', 'RomFS file')))

    a = parser.parse_args()
    opts = dict(_common.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    romfs_stat = os.stat(a.romfs)
    romfs_size = romfs_stat.st_size

    with open(a.romfs, 'rb') as f:
        mount = RomFSMount(romfs_fp=f, g_stat=romfs_stat)
        if _common.macos or _common.windows:
            opts['fstypename'] = 'RomFS'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            path_to_show = os.path.realpath(a.romfs).rsplit('/', maxsplit=2)
            if _common.macos:
                opts['volname'] = "Nintendo 3DS RomFS ({}/{})".format(path_to_show[-2], path_to_show[-1])
            elif _common.windows:
                # volume label can only be up to 32 chars
                # TODO: maybe I should show the path here, if i can shorten it properly
                opts['volname'] = "Nintendo 3DS RomFS"
        fuse = FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
                    fsname=os.path.realpath(a.romfs).replace(',', '_'), **opts)


if __name__ == '__main__':
    print('Note: You should be calling this script as "mount_{0}" or "{1} -mfuse3ds {0}" '
          'instead of calling it directly.'.format('romfs', _common.python_cmd))
    main()
