# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts CTR Cart Image (CCI, ".3ds") files, creating a virtual filesystem of separate partitions.
"""

import logging
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import argv
from typing import TYPE_CHECKING

from pyctr.type.cci import CCIReader, CCISection

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, load_custom_boot9, \
    realpath
from .ncch import NCCHContainerMount

if TYPE_CHECKING:
    from typing import Dict


class CTRCartImageMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, reader: 'CCIReader', g_stat: dict):
        self.dirs: Dict[str, NCCHContainerMount] = {}
        self.files: Dict[str, CCISection] = {}

        # get status change, modify, and file access times
        self.g_stat = g_stat

        self.reader = reader

    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass

    destroy = __del__

    def init(self, path):
        ncsd_part_names = ('game', 'manual', 'dlp', 'unk', 'unk', 'unk', 'update_n3ds', 'update_o3ds')

        def add_file(name: str, section: 'CCISection'):
            self.files[name] = section

        add_file('/ncsd.bin', CCISection.Header)
        add_file('/cardinfo.bin', CCISection.CardInfo)
        add_file('/devinfo.bin', CCISection.DevInfo)
        for part, ncch_reader in self.reader.contents.items():
            dirname = f'/content{part}.{ncsd_part_names[part]}'
            filename = dirname + '.ncch'

            add_file(filename, part)
            try:
                mount = NCCHContainerMount(ncch_reader, g_stat=self.g_stat)
                mount.init(path)
                self.dirs[dirname] = mount
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
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': self.reader.sections[self.files[path]].size, 'st_nlink': 1}
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

        section = self.files[path]
        with self.reader.open_raw_section(section) as f:
            f.seek(offset)
            return f.read(size)

    @_c.ensure_lower_path
    def statfs(self, path):
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].statfs(_c.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.reader.image_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS CTR Cart Image files.',
                            parents=(_c.default_argp, _c.ctrcrypto_argp, _c.main_args('cci', 'CCI file')))
    parser.add_argument('--dec', help='assume contents are decrypted', action='store_true')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    cci_stat = get_time(a.cci)

    load_custom_boot9(a.boot9)

    with CCIReader(a.cci, dev=a.dev, assume_decrypted=a.dec) as r:
        mount = CTRCartImageMount(reader=r, g_stat=cci_stat)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'CCI'
            if _c.macos:
                display = r.media_id.upper()
                try:
                    title = r.contents[CCISection.Application].exefs.icon.get_app_title()
                    display += f'; ' + r.contents[CCISection.Application].product_code
                    if title.short_desc != 'unknown':
                        display += '; ' + title.short_desc
                except:
                    pass
                opts['volname'] = f'CTR Cart Image ({display})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                try:
                    title = r.contents[CCISection.Application].exefs.icon.get_app_title().short_desc
                    if len(title) > 26:
                        title = title[0:25] + '\u2026'  # ellipsis
                    display = title
                except:
                    display = r.tmd.title_id.upper()
                opts['volname'] = f'CCI ({display})'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=realpath(a.cci).replace(',', '_'), **opts)
