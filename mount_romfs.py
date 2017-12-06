#!/usr/bin/env python3

import argparse
import errno
import hashlib
import logging
import math
import os
import stat
import struct
import sys

from pyctr import romfs, util

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ImportError:
    sys.exit('fuse module not found, please install fusepy to mount images '
             '(`pip3 install git+https://github.com/billziss-gh/fusepy.git`).')


class RomFSMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, romfs_fp, g_stat):
        # get status change, modify, and file access times
        self.g_stat = {'st_ctime': int(g_stat.st_ctime), 'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        romfs_fp.seek(0, 2)
        self.romfs_size = romfs_fp.tell()
        romfs_fp.seek(0)

        # open file, read IVFC header for lv3 offset
        self.f = romfs_fp
        ivfc_header = self.f.read(romfs.IVFC_HEADER_SIZE)
        lv3_offset = romfs.get_lv3_offset_from_ivfc(ivfc_header)

        self.f.seek(lv3_offset)
        lv3_header = self.f.read(romfs.ROMFS_LV3_HEADER_SIZE)
        self.romfs_reader = romfs.RomFSReader.from_lv3_header(lv3_header, case_insensitive=True)

        dirmeta_region = self.romfs_reader.dirmeta_region
        filemeta_region = self.romfs_reader.filemeta_region
        filedata_offset = self.romfs_reader.filedata_offset

        self.data_offset = lv3_offset + filedata_offset

        self.f.seek(lv3_offset + dirmeta_region.offset)
        dirmeta = self.f.read(dirmeta_region.size)
        self.f.seek(lv3_offset + filemeta_region.offset)
        filemeta = self.f.read(filemeta_region.size)

        self.romfs_reader.parse_metadata(dirmeta, filemeta)

    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        try:
            item = self.romfs_reader.get_info_from_path(path)
        except romfs.RomFSFileNotFoundException:
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
        except romfs.RomFSFileNotFoundException:
            raise FuseOSError(errno.ENOENT)
        return ['.', '..', *item.contents]

    def read(self, path, size, offset, fh):
        try:
            item = self.romfs_reader.get_info_from_path(path)
        except romfs.RomFSFileNotFoundException:
            raise FuseOSError(errno.ENOENT)
        self.f.seek(self.data_offset + item.offset + offset)
        return self.f.read(size)

    def statfs(self, path):
        try:
            item = self.romfs_reader.get_info_from_path(path)
        except romfs.RomFSFileNotFoundException:
            raise FuseOSError(errno.ENOENT)
        return {'f_bsize': 4096, 'f_blocks': self.romfs_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(item.contents)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS Read-only Filesystem (RomFS) files.')
    parser.add_argument('--fg', '-f', help='run in foreground', action='store_true')
    parser.add_argument('--do', help='debug output (python logging module)', action='store_true')
    parser.add_argument('-o', metavar='OPTIONS', help='mount options')
    parser.add_argument('romfs', help='RomFS file')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()
    try:
        opts = {o: True for o in a.o.split(',')}
    except AttributeError:
        opts = {}

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    romfs_stat = os.stat(a.romfs)
    romfs_size = os.path.getsize(a.romfs)

    with open(a.romfs, 'rb') as f:
        fuse = FUSE(RomFSMount(romfs_fp=f, g_stat=romfs_stat), a.mount_point, foreground=a.fg or a.do,
                    fsname=os.path.realpath(a.romfs), ro=True, nothreads=True, **opts)
