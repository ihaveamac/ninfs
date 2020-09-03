# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts Read-only Filesystem (RomFS) files, creating a virtual filesystem of the RomFS contents. Accepts ones with and
without an IVFC header (original HANS format).
"""

import logging
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import argv

from pyctr.type.romfs import RomFSReader, RomFSFileNotFoundError

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, realpath


class RomFSMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, reader: 'RomFSReader', g_stat: dict):
        # get status change, modify, and file access times
        self.g_stat = g_stat

        self.reader = reader

    def __del__(self, *args):
        try:
            self.reader.close()
        except AttributeError:
            pass

    destroy = __del__

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
            with self.reader.open(path) as f:
                f.seek(offset)
                return f.read(size)
        except (KeyError, RomFSFileNotFoundError):
            raise FuseOSError(ENOENT)

    def statfs(self, path):
        try:
            item = self.reader.get_info_from_path(path)
        except RomFSFileNotFoundError:
            raise FuseOSError(ENOENT)
        return {'f_bsize': 4096, 'f_blocks': self.reader.total_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(item.contents)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS Read-only Filesystem (RomFS) files.',
                            parents=(_c.default_argp, _c.main_args('romfs', 'RomFS file')))

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    romfs_stat = get_time(a.romfs)

    with RomFSReader(a.romfs, case_insensitive=True) as r:
        mount = RomFSMount(reader=r, g_stat=romfs_stat)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'RomFS'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            path_to_show = realpath(a.romfs).rsplit('/', maxsplit=2)
            if _c.macos:
                opts['volname'] = f'Nintendo 3DS RomFS ({path_to_show[-2]}/{path_to_show[-1]})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = 'Nintendo 3DS RomFS'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=realpath(a.romfs).replace(',', '_'), **opts)
