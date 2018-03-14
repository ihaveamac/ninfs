#!/usr/bin/env python3

"""
Mounts Read-only Filesystem (RomFS) files, creating a virtual filesystem of the RomFS contents. Accepts ones with and without an IVFC header (original HANS format).
"""

import argparse
import errno
import hashlib
import logging
import math
import os
import stat
import struct
import sys
from typing import BinaryIO

from . import common
from pyctr import romfs, util

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ModuleNotFoundError:
    sys.exit("fuse module not found, please install fusepy to mount images "
             "(`{} install https://github.com/billziss-gh/fusepy/archive/windows.zip`).".format(common.pip_command))
except Exception as e:
    sys.exit("Failed to import the fuse module:\n"
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
        self.f = romfs_fp

        self.romfs_reader = romfs.RomFSReader.load(romfs_fp, case_insensitive=False)

    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        try:
            item = self.romfs_reader.get_info_from_path(path)
        except romfs.RomFSFileNotFoundError:
            raise FuseOSError(errno.ENOENT)
        if item.type == 'dir':
            st = {'st_mode': (stat.S_IFDIR | 0o555), 'st_nlink': 2}
        elif item.type == 'file':
            st = {'st_mode': (stat.S_IFREG | 0o444), 'st_size': item.size, 'st_nlink': 1}
        else:
            # this won't happen unless I fucked up
            raise FuseOSError(errno.ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        try:
            item = self.romfs_reader.get_info_from_path(path)
        except romfs.RomFSFileNotFoundError:
            raise FuseOSError(errno.ENOENT)
        return ['.', '..', *item.contents]

    def read(self, path, size, offset, fh):
        try:
            item = self.romfs_reader.get_info_from_path(path)
        except romfs.RomFSFileNotFoundError:
            raise FuseOSError(errno.ENOENT)
        real_offset = item.offset + offset
        if real_offset > item.offset + item.size:
            # do I raise an exception or return nothing? I'm not sure
            return b''
        if offset + size > item.size:
            size = item.size - offset
        self.f.seek(self.romfs_reader.data_offset + real_offset)
        return self.f.read(size)

    def statfs(self, path):
        try:
            item = self.romfs_reader.get_info_from_path(path)
        except romfs.RomFSFileNotFoundError:
            raise FuseOSError(errno.ENOENT)
        return {'f_bsize': 4096, 'f_blocks': self.romfs_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(item.contents)}


def main():
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS Read-only Filesystem (RomFS) files.',
                                     parents=[common.default_argparser])
    parser.add_argument('romfs', help='RomFS file')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()
    opts = dict(common.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    romfs_stat = os.stat(a.romfs)
    romfs_size = os.path.getsize(a.romfs)

    with open(a.romfs, 'rb') as f:
        mount = RomFSMount(romfs_fp=f, g_stat=romfs_stat)
        if common.macos or common.windows:
            opts['fstypename'] = 'RomFS'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            path_to_show = os.path.realpath(a.romfs).rsplit('/', maxsplit=2)
            if common.macos:
                opts['volname'] = "Nintendo 3DS RomFS ({}/{})".format(path_to_show[-2], path_to_show[-1])
            elif common.windows:
                # volume label can only be up to 32 chars
                # TODO: maybe I should show the path here, if i can shorten it properly
                opts['volname'] = "Nintendo 3DS RomFS"
        fuse = FUSE(mount, a.mount_point, foreground=a.fg or a.do, ro=True, nothreads=True,
                    fsname=os.path.realpath(a.romfs).replace(',', '_'), **opts)


if __name__ == '__main__':
    main()
