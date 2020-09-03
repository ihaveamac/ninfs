# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts Nintendo DS ROM images, creating a virtual filesystem of the RomFS contents.
"""

import logging
from collections import defaultdict
from errno import ENOENT
from functools import lru_cache
from stat import S_IFDIR, S_IFREG
from struct import Struct, iter_unpack
from sys import argv
from typing import BinaryIO, NamedTuple

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, realpath

twl_header_format = ('<12s 4s 2s B B B 7x B B B B I I I I I I I I I I I I I I I I I I I H H I I Q I I 56x 156s HH 32x '
                     # twl stuff
                     '48x I 12x I 4x I I I 4x I I 48x I 12x 16x Q I I 176x 16x 3328x')


twl_header_struct = Struct(twl_header_format)


# TODO: probably ignore all this and just read the values we want
class TwlHeaderRaw(NamedTuple):
    game_title: bytes
    game_code: bytes
    maker_code: bytes
    unit_code: int
    seed_select: int
    device_capacity: int
    dsi_flags: int
    nds_region: int
    rom_version: int
    autostart: int
    arm9_rom_offset: int
    arm9_entry_address: int
    arm9_ram_address: int
    arm9_size: int
    arm7_rom_offset: int
    arm7_entry_address: int
    arm7_ram_address: int
    arm7_size: int
    fnt_offset: int
    fnt_size: int
    fat_offset: int
    fat_size: int
    arm9_overlay_offset: int
    arm9_overlay_size: int
    arm7_overlay_offset: int
    arm7_overlay_size: int
    rom_control_normal: int
    rom_control_key1: int
    icon_offset: int
    secure_area_crc: int
    secure_area_delay: int
    arm9_auto_load: int
    arm7_auto_load: int
    secure_area_disable: int
    ntr_rom_size: int
    header_size: int
    logo: bytes
    logo_crc: int
    header_crc: int
    region_flags: int
    arm9i_rom_offset: int
    arm9i_load_adress: int
    arm9i_size: int
    arm7i_rom_offset: int
    arm7i_load_adress: int
    arm7i_size: int
    ntr_twl_rom_size: int
    title_id: int
    pubsav_size: int
    prvsav_size: int


class SRLMount(LoggingMixIn, Operations):
    fd = 0

    @lru_cache()
    def parse_path(self, path: str):
        curr = self.hierarchy
        if path[0] == '/':
            path = path[1:]
        for part in path.split('/'):
            if part == '':
                break
            try:
                curr = curr['contents'][part]
            except KeyError:
                raise FuseOSError(ENOENT)
        return curr

    def __init__(self, srl_fp: BinaryIO, g_stat: dict):
        # get status change, modify, and file access times
        self.g_stat = g_stat

        # parse header
        header = TwlHeaderRaw(*twl_header_struct.unpack(srl_fp.read(0x1000)))
        self.title = header.game_title.decode('ascii').replace('\0', '')
        self.code = header.game_code.decode('ascii')
        self.total_size = 0x20000 << header.device_capacity

        self.hierarchy = {'type': 'dir', 'contents': {'header.bin': {'name': 'header.bin', 'type': 'file', 'offset': 0,
                                                                     'size': 0x1000 if header.unit_code else 0x200}}}

        if header.arm7_rom_offset:
            self.hierarchy['contents']['arm7.bin'] = {'name': 'arm7.bin', 'type': 'file',
                                                      'offset': header.arm7_rom_offset, 'size': header.arm7_size}

        if header.arm9_rom_offset:
            f_size = header.arm9_size
            srl_fp.seek(header.arm9_rom_offset + header.arm9_size)
            if int.from_bytes(srl_fp.read(4), 'little') == 0xDEC00621:
                f_size += 0xC
            self.hierarchy['contents']['arm9.bin'] = {'name': 'arm9.bin', 'type': 'file',
                                                      'offset': header.arm9_rom_offset, 'size': f_size}

        if header.arm7i_rom_offset:
            self.hierarchy['contents']['arm7i.bin'] = {'name': 'arm7i.bin', 'type': 'file',
                                                       'offset': header.arm7i_rom_offset, 'size': header.arm7i_size}

        if header.arm9i_rom_offset:
            self.hierarchy['contents']['arm9i.bin'] = {'name': 'arm9i.bin', 'type': 'file',
                                                       'offset': header.arm9i_rom_offset, 'size': header.arm9i_size}

        if header.arm9_overlay_offset:
            self.hierarchy['contents']['arm9overlay.bin'] = {'name': 'arm9overlay.bin', 'type': 'file',
                                                             'offset': header.arm9_overlay_offset,
                                                             'size': header.arm9_overlay_size}

        if header.arm7_overlay_offset:
            self.hierarchy['contents']['arm7overlay.bin'] = {'name': 'arm7overlay.bin', 'type': 'file',
                                                             'offset': header.arm7_overlay_offset,
                                                             'size': header.arm7_overlay_size}

        if header.icon_offset:
            srl_fp.seek(header.icon_offset)
            ver = int.from_bytes(srl_fp.read(2), 'little')
            sizes = defaultdict(lambda: 0, {0x0001: 0x0840, 0x0002: 0x0940, 0x0003: 0x1240, 0x0103: 0x23C0})
            self.hierarchy['contents']['banner.bin'] = {'name': 'banner.bin', 'type': 'file',
                                                        'offset': header.icon_offset, 'size': sizes[ver]}

        if header.fnt_offset:
            self.hierarchy['contents']['data'] = {'name': 'data', 'type': 'dir', 'contents': {}}

            # generate hierarchy
            srl_fp.seek(header.fnt_offset)
            fnt = srl_fp.read(header.fnt_size)

            main_table = fnt[0:int.from_bytes(fnt[6:8], 'little') * 8]

            dirs_by_id: dict = defaultdict(dict)
            files_by_id = {}

            # sub-table offset, id of first file in sub-table, parent directory id
            for idx, raw_ent in enumerate(iter_unpack('<IHH', main_table), 0xF000):
                sto, ffid, pdid = raw_ent  # type: int
                ent = dirs_by_id[idx]
                ent['id'] = idx
                ent['contents'] = []
                ent['first id'] = ffid
                ent['sub-table offset'] = sto
                if idx == 0xF000:
                    ent['name'] = None
                    ent['parent'] = None
                else:
                    ent['name'] = f'unk_{idx:#6x}'
                    ent['parent'] = dirs_by_id[pdid]
                    dirs_by_id[pdid]['contents'].append(ent)

            for dir_id, ent in dirs_by_id.items():
                offs = ent['sub-table offset']
                cur_id = ent['first id']
                while True:
                    type_len = fnt[offs]
                    if type_len == 0:
                        break
                    name_len = type_len & 0x7F
                    is_dir = type_len & 0x80
                    offs += 1
                    name = fnt[offs:offs + name_len].decode('shift-jis')
                    offs += name_len
                    if is_dir:
                        dir_id = int.from_bytes(fnt[offs:offs + 2], 'little')
                        offs += 2
                        dirs_by_id[dir_id]['name'] = name
                    else:
                        file_ent = {'id': cur_id, 'parent': ent, 'name': name}
                        files_by_id[cur_id] = file_ent
                        ent['contents'].append(file_ent)
                        cur_id += 1

            srl_fp.seek(header.fat_offset)
            fat = srl_fp.read(header.fat_size)

            def iterdir(dir_ent, hierarchy_ent):
                for c in dir_ent['contents']:
                    ent = {'name': c['name']}
                    hierarchy_ent['contents'][c['name'].lower()] = ent
                    if c['id'] >= 0xF000:
                        ent['type'] = 'dir'
                        ent['contents'] = {}
                        iterdir(c, ent)
                    else:
                        ent['type'] = 'file'
                        fat_ent_off: int = c['id'] * 8
                        ent['offset'] = int.from_bytes(fat[fat_ent_off:fat_ent_off + 4], 'little')
                        ent['size'] = int.from_bytes(fat[fat_ent_off + 4:fat_ent_off + 8], 'little') - ent['offset']

            iterdir(dirs_by_id[0xF000], self.hierarchy['contents']['data'])

        self.f = srl_fp

    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass

    destroy = __del__

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        item = self.parse_path(path)
        if item['type'] == 'dir':
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        elif item['type'] == 'file':
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': item['size'], 'st_nlink': 1}
        else:
            # this won't happen unless I fucked up
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    @_c.ensure_lower_path
    def open(self, path, flags):
        self.fd += 1
        return self.fd

    @_c.ensure_lower_path
    def readdir(self, path, fh):
        item = self.parse_path(path)
        yield from ('.', '..')
        yield from (c['name'] for c in item['contents'].values())

    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        item = self.parse_path(path)
        if item['offset'] + offset > item['offset'] + item['size']:
            return b''
        if offset + size > item['size']:
            size = item['size'] - offset
        self.f.seek(item['offset'] + offset)
        return self.f.read(size)

    def statfs(self, path):
        return {'f_bsize': 4096, 'f_blocks': self.total_size // 4096, 'f_bavail': 0, 'f_bfree': 0}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo DS ROM images.',
                            parents=(_c.default_argp, _c.main_args('srl', 'NDS/SRL file')))

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    srl_stat = get_time(a.srl)

    with open(a.srl, 'rb') as f:
        mount = SRLMount(srl_fp=f, g_stat=srl_stat)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'SRL'
            opts['volname'] = f'Nintendo DS ROM ({mount.title})'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=realpath(a.srl).replace(',', '_'), **opts)
