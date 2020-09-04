# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts NCCH containers, creating a virtual filesystem of decrypted sections.
"""

import logging
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import argv
from typing import TYPE_CHECKING

from pyctr.crypto import load_seeddb
from pyctr.type.ncch import NCCHReader, NCCHSection

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, load_custom_boot9, \
    realpath
from .exefs import ExeFSMount
from .romfs import RomFSMount

if TYPE_CHECKING:
    from typing import Dict


class NCCHContainerMount(LoggingMixIn, Operations):
    fd = 0
    romfs_fuse = None
    exefs_fuse = None

    def __init__(self, reader: 'NCCHReader', g_stat: dict):
        self.files: Dict[str, NCCHSection] = {}

        # get status change, modify, and file access times
        self.g_stat = g_stat

        self.reader = reader

    def __del__(self, *args):
        try:
            self.reader.close()
        except AttributeError:
            pass

    destroy = __del__

    def init(self, path, _setup_romfs=True):
        decrypted_filename = '/decrypted.' + ('cxi' if self.reader.flags.executable else 'cfa')

        self.files[decrypted_filename] = NCCHSection.FullDecrypted
        self.files['/ncch.bin'] = NCCHSection.Header

        if NCCHSection.ExtendedHeader in self.reader.sections:
            self.files['/extheader.bin'] = NCCHSection.ExtendedHeader

        if NCCHSection.Logo in self.reader.sections:
            self.files['/logo.bin'] = NCCHSection.Logo

        if NCCHSection.Plain in self.reader.sections:
            self.files['/plain.bin'] = NCCHSection.Plain

        if NCCHSection.ExeFS in self.reader.sections:
            self.files['/exefs.bin'] = NCCHSection.ExeFS
            self.exefs_fuse = ExeFSMount(self.reader.exefs, g_stat=self.g_stat, decompress_code=True)
            self.exefs_fuse.init(path)

        if NCCHSection.RomFS in self.reader.sections:
            self.files['/romfs.bin'] = NCCHSection.RomFS
            self.romfs_fuse = RomFSMount(self.reader.romfs, g_stat=self.g_stat)

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        if path.startswith('/exefs/'):
            return self.exefs_fuse.getattr(_c.remove_first_dir(path), fh)
        elif path.startswith('/romfs/'):
            return self.romfs_fuse.getattr(_c.remove_first_dir(path), fh)
        uid, gid, pid = fuse_get_context()
        if path in {'/', '/romfs', '/exefs'}:
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        elif path in self.files:
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': self.reader.sections[self.files[path]].size, 'st_nlink': 1}
        else:
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    @_c.ensure_lower_path
    def readdir(self, path, fh):
        if path.startswith('/exefs'):
            yield from self.exefs_fuse.readdir(_c.remove_first_dir(path), fh)
        elif path.startswith('/romfs'):
            yield from self.romfs_fuse.readdir(_c.remove_first_dir(path), fh)
        elif path == '/':
            yield from ('.', '..')
            yield from (x[1:] for x in self.files)
            if self.exefs_fuse is not None:
                yield 'exefs'
            if self.romfs_fuse is not None:
                yield 'romfs'

    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        if path.startswith('/exefs/'):
            return self.exefs_fuse.read(_c.remove_first_dir(path), size, offset, fh)
        elif path.startswith('/romfs/'):
            return self.romfs_fuse.read(_c.remove_first_dir(path), size, offset, fh)

        section = self.files[path]
        with self.reader.open_raw_section(section) as f:
            f.seek(offset)
            return f.read(size)

    @_c.ensure_lower_path
    def statfs(self, path):
        if path.startswith('/exefs/'):
            return self.exefs_fuse.statfs(_c.remove_first_dir(path))
        elif path.startswith('/romfs/'):
            return self.romfs_fuse.statfs(_c.remove_first_dir(path))
        else:
            return {'f_bsize': 4096, 'f_blocks': self.reader.content_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                    'f_files': len(self.files)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS NCCH containers.',
                            parents=(_c.default_argp, _c.ctrcrypto_argp, _c.seeddb_argp,
                                     _c.main_args('ncch', 'NCCH file')))
    parser.add_argument('--dec', help='assume contents are decrypted', action='store_true')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    ncch_stat = get_time(a.ncch)

    load_custom_boot9(a.boot9)

    if a.seeddb:
        load_seeddb(a.seeddb)

    with NCCHReader(a.ncch, dev=a.dev, assume_decrypted=a.dec, seed=a.seed) as r:
        mount = NCCHContainerMount(reader=r, g_stat=ncch_stat)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'NCCH'
            if _c.macos:
                display = f'{r.partition_id:016X}; {r.product_code}'
                try:
                    title = r.exefs.icon.get_app_title()
                    if title.short_desc != 'unknown':
                        display += '; ' + title.short_desc
                except:
                    pass
                opts['volname'] = f'NCCH Container ({display})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                try:
                    title = r.exefs.icon.get_app_title().short_desc
                    if len(title) > 26:
                        title = title[0:25] + '\u2026'  # ellipsis
                    display = title
                except:
                    display = r.tmd.title_id.upper()
                opts['volname'] = f'NCCH ({display})'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=realpath(a.ncch).replace(',', '_'), **opts)
