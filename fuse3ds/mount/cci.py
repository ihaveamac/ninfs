# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts CTR Cart Image (CCI, ".3ds") files, creating a virtual filesystem of separate partitions.
"""

import logging
import os
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import exit, argv
from typing import TYPE_CHECKING, BinaryIO

from pyctr.util import readle
from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
from .ncch import NCCHContainerMount

if TYPE_CHECKING:
    from typing import Dict


class CTRCartImageMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, cci_fp: BinaryIO, g_stat: os.stat_result, dev: bool = False, seeddb: str = None):
        self.dev = dev
        self.seeddb = seeddb

        self._g_stat = g_stat
        # get status change, modify, and file access times
        self.g_stat = {'st_ctime': int(g_stat.st_ctime),
                       'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        # open cci and get section sizes
        cci_fp.seek(0x100)
        self.ncsd_header = cci_fp.read(0x100)
        if self.ncsd_header[0:4] != b'NCSD':
            exit('NCSD magic not found, is this a real CCI?')
        self.media_id = self.ncsd_header[0x8:0x10]
        if self.media_id == b'\0' * 8:
            exit('Media ID is all-zero, is this a CCI?')

        self.cci_size = readle(self.ncsd_header[4:8]) * 0x200

        # create initial virtual files
        self.files = {'/ncsd.bin': {'size': 0x200, 'offset': 0},
                      '/cardinfo.bin': {'size': 0x1000, 'offset': 0x200},
                      '/devinfo.bin': {'size': 0x300, 'offset': 0x1200}}

        self.f = cci_fp

        self.dirs: Dict[str, NCCHContainerMount] = {}

    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass

    destroy = __del__

    def init(self, path):
        ncsd_part_raw = self.ncsd_header[0x20:0x60]
        ncsd_partitions = [[readle(ncsd_part_raw[i:i + 4]) * 0x200,
                            readle(ncsd_part_raw[i + 4:i + 8]) * 0x200] for i in range(0, 0x40, 0x8)]

        ncsd_part_names = ('game', 'manual', 'dlp', 'unk', 'unk', 'unk', 'update_n3ds', 'update_o3ds')

        for idx, part in enumerate(ncsd_partitions):
            if part[0]:
                filename = f'/content{idx}.{ncsd_part_names[idx]}.ncch'
                self.files[filename] = {'size': part[1], 'offset': part[0]}

                dirname = f'/content{idx}.{ncsd_part_names[idx]}'
                # noinspection PyBroadException
                try:
                    content_vfp = _c.VirtualFileWrapper(self, filename, part[1])
                    content_fuse = NCCHContainerMount(content_vfp, g_stat=self._g_stat, dev=self.dev,
                                                      seeddb=self.seeddb)
                    content_fuse.init(path)
                    self.dirs[dirname] = content_fuse
                except Exception as e:
                    print(f'Failed to mount {filename}: {type(e).__name__}: {e}')

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].getattr(_c.remove_first_dir(path), fh)
        uid, gid, pid = fuse_get_context()
        if path == '/':
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
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            yield from self.dirs[first_dir].readdir(_c.remove_first_dir(path), fh)
        else:
            yield from ('.', '..')
            yield from (x[1:] for x in self.files)
            yield from (x[1:] for x in self.dirs)

    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].read(_c.remove_first_dir(path), size, offset, fh)
        fi = self.files[path]
        if fi['offset'] + offset > fi['offset'] + fi['size']:
            return b''
        if offset + size > fi['size']:
            size = fi['size'] - offset
        real_offset = fi['offset'] + offset
        self.f.seek(real_offset)
        return self.f.read(size)

    @_c.ensure_lower_path
    def statfs(self, path):
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].statfs(_c.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.cci_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS CTR Cart Image files.',
                            parents=(_c.default_argp, _c.dev_argp, _c.seeddb_argp,
                                     _c.main_args('cci', 'CCI file')))

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    cci_stat = os.stat(a.cci)

    with open(a.cci, 'rb') as f:
        mount = CTRCartImageMount(cci_fp=f, dev=a.dev, g_stat=cci_stat, seeddb=a.seeddb)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'CCI'
            if _c.macos:
                opts['volname'] = f'CTR Cart Image ({mount.media_id[::-1].hex().upper()})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = f'CCI ({mount.media_id[::-1].hex().upper()})'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=os.path.realpath(a.cci).replace(',', '_'), **opts)
