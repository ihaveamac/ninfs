# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts 3DSX Homebrew files, creating a virtual filesystem with the 3DSX's RomFS and SMDH.
"""

import logging
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from struct import unpack
from sys import exit, argv
from typing import TYPE_CHECKING, BinaryIO

from pyctr.type.romfs import RomFSReader
from pyctr.util import readle

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, realpath
from .romfs import RomFSMount

if TYPE_CHECKING:
    from typing import Dict


class ThreeDSXMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, threedsx_fp: BinaryIO, g_stat: dict):
        self.g_stat = g_stat
        self.romfs_fuse: RomFSMount = None

        self.f = threedsx_fp
        threedsx_fp.seek(0, 2)
        self.total_size = threedsx_fp.tell()
        threedsx_fp.seek(0)

        header = threedsx_fp.read(0x20)
        if readle(header[4:6]) < 44:
            exit('3DSX has no SMDH or RomFS.')

        smdh_offset, smdh_size, romfs_offset = unpack('<3I', threedsx_fp.read(12))  # type: int
        self.files: Dict[str, Dict[str, int]] = {}
        if smdh_offset:  # unlikely, you can't add a romfs without this
            self.files['/icon.smdh'] = {'size': smdh_size, 'offset': smdh_offset}
        if romfs_offset:
            self.files['/romfs.bin'] = {'size': self.total_size - romfs_offset, 'offset': romfs_offset}

    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass

    destroy = __del__

    def init(self, path):
        if '/romfs.bin' in self.files:
            try:
                romfs_vfp = _c.VirtualFileWrapper(self, '/romfs.bin', self.files['/romfs.bin']['size'])
                romfs_reader = RomFSReader(romfs_vfp)
                romfs_fuse = RomFSMount(romfs_reader, self.g_stat)
                romfs_fuse.init(path)
                self.romfs_fuse = romfs_fuse
            except Exception as e:
                print(f'Failed to mount RomFS: {type(e).__name__}: {e}')

    def flush(self, path, fh):
        return self.f.flush()

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        if path.startswith('/romfs/'):
            return self.romfs_fuse.getattr(_c.remove_first_dir(path), fh)
        uid, gid, pid = fuse_get_context()
        if path == '/' or path == '/romfs':
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        elif path in self.files:
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': self.files[path]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    @_c.ensure_lower_path
    def readdir(self, path, fh):
        if path.startswith('/romfs'):
            yield from self.romfs_fuse.readdir(_c.remove_first_dir(path), fh)
        elif path == '/':
            yield from ('.', '..')
            yield from (x[1:] for x in self.files)
            if self.romfs_fuse is not None:
                yield 'romfs'

    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        if path.startswith('/romfs/'):
            return self.romfs_fuse.read(_c.remove_first_dir(path), size, offset, fh)

        fi = self.files[path]
        real_offset = fi['offset'] + offset
        if fi['offset'] + offset > fi['offset'] + fi['size']:
            return b''
        if offset + size > fi['size']:
            size = fi['size'] - offset
        self.f.seek(real_offset)
        return self.f.read(size)

    @_c.ensure_lower_path
    def statfs(self, path):
        if path.startswith('/romfs/'):
            return self.romfs_fuse.statfs(_c.remove_first_dir(path))
        else:
            return {'f_bsize': 4096, 'f_blocks': self.total_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                    'f_files': len(self.files)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount 3DSX Homebrew files.',
                            parents=(_c.default_argp, _c.main_args('threedsx', '3DSX file')))

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    threedsx_stat = get_time(a.threedsx)

    with open(a.threedsx, 'rb') as f:
        mount = ThreeDSXMount(threedsx_fp=f, g_stat=threedsx_stat)
        if _c.macos or _c.windows:
            opts['fstypename'] = '3DSX'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            path_to_show = realpath(a.threedsx).rsplit('/', maxsplit=2)
            if _c.macos:
                opts['volname'] = f'3DSX Homebrew ({path_to_show[-2]}/{path_to_show[-1]})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = '3DSX Homebrew'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=realpath(a.threedsx).replace(',', '_'), **opts)
