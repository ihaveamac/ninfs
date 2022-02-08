# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts raw CDN contents, creating a virtual filesystem of decrypted contents (if encrypted).
"""

import logging
from errno import ENOENT
from os.path import isfile, join
from stat import S_IFDIR, S_IFREG
from sys import argv
from typing import TYPE_CHECKING

from pyctr.crypto import load_seeddb
from pyctr.type.cdn import CDNReader, CDNSection

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, load_custom_boot9, \
    realpath
from .ncch import NCCHContainerMount
from .srl import SRLMount

if TYPE_CHECKING:
    from typing import Dict, Tuple, Union


class CDNContentsMount(LoggingMixIn, Operations):
    fd = 0
    total_size = 0

    def __init__(self, reader: 'CDNReader', g_stat: dict):
        self.dirs: Dict[str, Union[NCCHContainerMount, SRLMount]] = {}
        self.files: Dict[str, Tuple[Union[int, CDNSection], int, int]] = {}

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
        def add_file(name: str, section: 'Union[CDNSection, int]', added_offset: int = 0):
            # added offset is used for a few things like meta icon and tmdchunks
            if section >= 0:
                size = self.reader.content_info[section].size
            else:
                with self.reader.open_raw_section(section) as f:
                    size = f.seek(0, 2)
            self.files[name] = (section, added_offset, size - added_offset)

        if CDNSection.Ticket in self.reader.available_sections:
            add_file('/ticket.bin', CDNSection.Ticket)
        add_file('/tmd.bin', CDNSection.TitleMetadata)
        add_file('/tmdchunks.bin', CDNSection.TitleMetadata, 0xB04)

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

            self.total_size += record.size

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].getattr(_c.remove_first_dir(path), fh)
        uid, gid, pid = fuse_get_context()
        if path == '/' or path in self.dirs:
            st = {'st_mode': (S_IFDIR | 0o777), 'st_nlink': 2}
        elif path in self.files:
            st = {'st_mode': (S_IFREG | 0o666), 'st_size': self.files[path][2], 'st_nlink': 1}
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
        return {'f_bsize': 4096, 'f_frsize': 4096, 'f_blocks': self.total_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS CDN contents.',
                            parents=(_c.default_argp, _c.ctrcrypto_argp, _c.seeddb_argp,
                                     _c.main_args('content', 'tmd file or directory with CDN contents')))
    parser.add_argument('--dec-key', help='decrypted titlekey')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    if isfile(a.content):
        tmd_file = a.content
    else:
        tmd_file = join(a.content, 'tmd')

    cdn_stat = get_time(a.content)

    load_custom_boot9(a.boot9)

    if a.seeddb:
        load_seeddb(a.seeddb)

    dec_key = None
    if a.dec_key:
        dec_key = bytes.fromhex(a.dec_key)

    with CDNReader(tmd_file, dev=a.dev, seed=a.seed, case_insensitive=True, decrypted_titlekey=dec_key) as r:
        mount = CDNContentsMount(reader=r, g_stat=cdn_stat)
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
                opts['volname'] = f'CDN Contents ({display})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                try:
                    title = r.contents[0].exefs.icon.get_app_title().short_desc
                    if len(title) > 26:
                        title = title[0:25] + '\u2026'  # ellipsis
                    display = title
                except:
                    display = r.tmd.title_id.upper()
                opts['volname'] = f'CDN ({display})'
        FUSE(mount, a.mount_point, foreground=a.fg or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=realpath(tmd_file).replace(',', '_'), **opts)
