# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts CTR Importable Archive (CIA) files, creating a virtual filesystem of decrypted contents (if encrypted) + Ticket,
Title Metadata, and Meta region (if exists).

DLC with missing contents is currently not supported.
"""

import logging
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import argv
from typing import TYPE_CHECKING

from pyctr.crypto import load_seeddb
from pyctr.type.cia import CIAReader, CIASection

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, load_custom_boot9, \
    realpath
from .ncch import NCCHContainerMount
from .srl import SRLMount

if TYPE_CHECKING:
    from typing import Dict, Tuple, Union


class CTRImportableArchiveMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, reader: 'CIAReader', g_stat: dict):
        self.dirs: Dict[str, Union[NCCHContainerMount, SRLMount]] = {}
        self.files: Dict[str, Tuple[Union[int, CIASection], int, int]] = {}

        # get status change, modify, and file access times
        self.g_stat = g_stat

        self.reader = reader

    def __del__(self, *args):
        try:
            self.reader.close()
        except AttributeError:
            pass

    destroy = __del__

    def init(self, path):
        def add_file(name: str, section: 'CIASection', added_offset: int = 0):
            # added offset is used for a few things like meta icon and tmdchunks
            region = self.reader.sections[section]
            self.files[name] = (section, added_offset, region.size - added_offset)

        add_file('/header.bin', CIASection.ArchiveHeader)
        add_file('/cert.bin', CIASection.CertificateChain)
        add_file('/ticket.bin', CIASection.Ticket)
        add_file('/tmd.bin', CIASection.TitleMetadata)
        add_file('/tmdchunks.bin', CIASection.TitleMetadata, 0xB04)
        if CIASection.Meta in self.reader.sections:
            add_file('/meta.bin', CIASection.Meta)
            add_file('/icon.bin', CIASection.Meta, 0x400)

        for record in self.reader.content_info:
            dirname = f'/{record.cindex:04x}.{record.id}'
            is_srl = record.cindex == 0 and self.reader.tmd.title_id[3:5] == '48'
            file_ext = 'nds' if is_srl else 'ncch'
            filename = f'{dirname}.{file_ext}'
            add_file(filename, record.cindex)
            try:
                if is_srl:
                    # special case for SRL contents
                    srl_fp = self.reader.open_raw_section(record.cindex)
                    self.dirs[dirname] = SRLMount(srl_fp, g_stat=self.g_stat)
                else:
                    mount = NCCHContainerMount(self.reader.contents[record.cindex], g_stat=self.g_stat)
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
        if path == '/' or path in self.dirs:
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        elif path in self.files:
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': self.files[path][2], 'st_nlink': 1}
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
        with self.reader.open_raw_section(section[0]) as f:
            f.seek(offset + section[1])
            return f.read(size)

    @_c.ensure_lower_path
    def statfs(self, path):
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].statfs(_c.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.reader.total_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS CTR Importable Archive files.',
                            parents=(_c.default_argp, _c.ctrcrypto_argp, _c.seeddb_argp,
                                     _c.main_args('cia', "CIA file")))

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    cia_stat = get_time(a.cia)

    load_custom_boot9(a.boot9)

    if a.seeddb:
        load_seeddb(a.seeddb)

    with CIAReader(a.cia, dev=a.dev, seed=a.seed) as r:
        mount = CTRImportableArchiveMount(reader=r, g_stat=cia_stat)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'CIA'
            if _c.macos:
                display = r.tmd.title_id.upper()
                try:
                    title = r.contents[0].exefs.icon.get_app_title()
                    display += f'; ' + r.contents[0].product_code
                    if title.short_desc != 'unknown':
                        display += '; ' + title.short_desc
                except:
                    pass
                opts['volname'] = f'CTR Importable Archive ({display})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                try:
                    title = r.contents[0].exefs.icon.get_app_title().short_desc
                    if len(title) > 26:
                        title = title[0:25] + '\u2026'  # ellipsis
                    display = title
                except:
                    display = r.tmd.title_id.upper()
                opts['volname'] = f'CIA ({display})'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=realpath(a.cia).replace(',', '_'), **opts)
