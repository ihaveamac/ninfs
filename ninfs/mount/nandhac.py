# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

import logging
import os
from collections import defaultdict
from errno import ENOENT, EROFS
from inspect import cleandoc
from stat import S_IFDIR, S_IFREG
from sys import argv, exit
from typing import TYPE_CHECKING
from zlib import crc32

from hac.crypto import XTSN, parse_biskeydump
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, realpath
from . import _common as _c

if TYPE_CHECKING:
    from typing import BinaryIO, List, TextIO

bis_key_ids = defaultdict(lambda: -1, {
    'PRODINFO': 0,
    'PRODINFOF': 0,
    'SAFE': 1,
    'SYSTEM': 2,
    'USER': 3
})


class HACNandImageMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, nand_fp: 'BinaryIO', g_stat: dict, keys: str, readonly: bool = False, emummc: int = None,
                 partition: str = None):
        self.base_addr = emummc or 0
        self.readonly = readonly
        self.g_stat = g_stat

        bis_keys = parse_biskeydump(keys)
        self.crypto: List[XTSN] = [None] * 4
        for x in range(4):
            try:
                self.crypto[x] = XTSN(*bis_keys[x])
            except TypeError:
                print(f"Couldn't get BIS KEY {x}. The associated partition(s) will not be available.")
                self.crypto[x] = None

        self.files = {}
        if partition:
            # we can probably assume this is a real file, and therefore can seek to the end this way...
            part_name = partition.upper()
            nand_fp.seek(0, 2)
            size = nand_fp.tell()
            self.files[f'/{part_name.lower()}.img'] = {'real_filename': part_name + '.img',
                                                       'bis_key': bis_key_ids[part_name],
                                                       'start': 0, 'end': size}
        else:
            nand_fp.seek(0x200 + self.base_addr)
            gpt_header = nand_fp.read(0x5C)
            if gpt_header[0:8] != b'EFI PART':
                exit('GPT header magic not found.')

            header_to_hash = gpt_header[0:0x10] + b'\0\0\0\0' + gpt_header[0x14:]
            crc_expected = int.from_bytes(gpt_header[0x10:0x14], 'little')
            crc_got = crc32(header_to_hash) & 0xFFFFFFFF
            if crc_got != crc_expected:
                exit(f'GPT header crc32 mismatch (expected {crc_expected:08x}, got {crc_got:08x})')

            gpt_backup_header_location = int.from_bytes(gpt_header[0x20:0x28], 'little')
            # check if the backup header exists
            nand_fp.seek(gpt_backup_header_location * 0x200 + self.base_addr)
            gpt_backup_header = nand_fp.read(0x200)
            if gpt_backup_header[0:8] != b'EFI PART':
                if emummc:
                    # it seems sometimes the backup header is not found in an emummc image
                    print('Warning: GPT backup header not found.')
                else:
                    exit('GPT backup header not found. This likely means an incomplete backup.')

            gpt_part_start = int.from_bytes(gpt_header[0x48:0x50], 'little')
            gpt_part_count = int.from_bytes(gpt_header[0x50:0x54], 'little')
            gpt_part_entry_size = int.from_bytes(gpt_header[0x54:0x58], 'little')

            nand_fp.seek(gpt_part_start * 0x200 + self.base_addr)
            gpt_part_full_raw = nand_fp.read(gpt_part_count * gpt_part_entry_size)
            gpt_part_crc_expected = int.from_bytes(gpt_header[0x58:0x5C], 'little')
            gpt_part_crc_got = crc32(gpt_part_full_raw) & 0xFFFFFFFF
            if gpt_part_crc_got != gpt_part_crc_expected:
                exit(f'GPT Partition table crc32 mismatch '
                     f'(expected {gpt_part_crc_expected:08x}, got {gpt_part_crc_got:08x})')
            gpt_parts_raw = [gpt_part_full_raw[i:i + gpt_part_entry_size] for i in range(0, len(gpt_part_full_raw),
                                                                                         gpt_part_entry_size)]
            for part in gpt_parts_raw:
                name = part[0x38:].decode('utf-16le').rstrip('\0')
                # check if we have a key for this partition
                if self.crypto[bis_key_ids[name]] is not None:
                    self.files[f'/{name.lower()}.img'] = {'real_filename': name + '.img', 'bis_key': bis_key_ids[name],
                                                          'start': int.from_bytes(part[0x20:0x28], 'little') * 0x200,
                                                          'end': (int.from_bytes(part[0x28:0x30], 'little') + 1) * 0x200}

        self.f = nand_fp

    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass

    destroy = __del__

    def flush(self, path, fh):
        return self.f.flush()

    @_c.ensure_lower_path
    def getattr(self, path: str, fh=None):
        uid, gid, pid = fuse_get_context()
        if path == '/':
            st = {'st_mode': (S_IFDIR | (0o555 if self.readonly else 0o777)), 'st_nlink': 2}
        elif path in self.files:
            p = self.files[path]
            st = {'st_mode': (S_IFREG | (0o444 if self.readonly else 0o666)),
                  'st_size': p['end'] - p['start'], 'st_nlink': 1}
        else:
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path: str, flags):
        self.fd += 1
        return self.fd

    @_c.ensure_lower_path
    def readdir(self, path: str, fh):
        yield from ('.', '..')
        yield from (x['real_filename'] for x in self.files.values())

    @_c.ensure_lower_path
    def read(self, path: str, size: int, offset: int, fh):
        fi = self.files[path]
        real_offset: int = fi['start'] + offset

        if fi['start'] + offset > fi['end']:
            return b''
        if offset + size > fi['end']:
            size = fi['end'] - offset

        if fi['bis_key'] >= 0:
            before = offset % 16
            after = (offset + size) % 16
            if after:
                after = 16 - after
            aligned_real_offset = real_offset - before
            aligned_offset = offset - before
            size = before + size
            self.f.seek(aligned_real_offset + self.base_addr)
            xtsn = self.crypto[fi['bis_key']]
            return xtsn.decrypt(self.f.read(size + after), 0, 0x4000, aligned_offset)[before:size]

        else:
            self.f.seek(real_offset + self.base_addr)
            return self.f.read(size)

    @_c.ensure_lower_path
    def write(self, path: str, data: bytes, offset: int, fh):
        if self.readonly:
            raise FuseOSError(EROFS)

        fi = self.files[path]
        real_offset: int = fi['start'] + offset
        real_len = len(data)

        if fi['start'] + offset > fi['end']:
            # not writing past the file size
            return real_len

        if real_offset + real_len > fi['end']:
            data = data[:-((real_offset + real_len) - (fi['end'] - fi['start']))]

        if fi['bis_key'] >= 0:
            before = offset % 16
            after = (offset + real_len) % 16
            aligned_offset = offset - before
            aligned_real_offset = real_offset - before
            if after:
                # this sucks...
                new_after = 16 - after
                last_block_ending = self.read(path, new_after, offset + len(data), 0)
            else:
                last_block_ending = b''

            if before:
                first_block_beginning = self.read(path, before, offset - before, 0)
            else:
                first_block_beginning = b''

            self.f.seek(aligned_real_offset + self.base_addr)
            xtsn = self.crypto[fi['bis_key']]
            to_encrypt = b''.join((first_block_beginning, data, last_block_ending))
            self.f.write(xtsn.encrypt(to_encrypt, 0, 0x4000, aligned_offset))

        else:
            self.f.seek(real_offset + self.base_addr)
            self.f.write(data)

        return real_len

    # TODO: get the real nand size, instead of hard-coding it
    @_c.ensure_lower_path
    def statfs(self, path: str):
        return {'f_bsize': 4096, 'f_blocks': 0x747C00000 // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser, RawDescriptionHelpFormatter
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo Switch NAND images.',
                            parents=(_c.default_argp, _c.readonly_argp,
                                     _c.main_args('image', 'NAND image or encrypted partition')),
                            formatter_class=RawDescriptionHelpFormatter,
                            epilog=cleandoc('''
                            partitions:
                              PRODINFO  (BIS Key 0)
                              PRODINFOF (BIS Key 0)
                              SAFE      (BIS Key 1)
                              SYSTEM    (BIS Key 2)
                              USER      (BIS KEY 3)
                            '''))
    parser.add_argument('--keys', help='keys file from biskeydump or Lockpick_RCM',
                        default=os.path.join(os.path.expanduser('~'), '.switch', 'prod.keys'))
    parser.add_argument('-S', '--split-files', help='treat as part of a split file', action='store_true')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-e', '--emummc', help='is an emuMMC image', action='store_const', const=0x800000)
    group.add_argument('-R', '--raw-emummc', help='is an SD raw emuMMC image', action='store_const', const=0x1800000)
    group.add_argument('--partition', metavar='PARTNAME', help='is a single encrypted partition')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    def do_thing(f: 'BinaryIO', k: 'TextIO', nand_stat: dict):
        mount = HACNandImageMount(nand_fp=f, g_stat=nand_stat, keys=k.read(), readonly=a.ro,
                                  emummc=a.emummc or a.raw_emummc, partition=a.partition)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'HACFS'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            if _c.macos:
                path_to_show = realpath(a.image).rsplit('/', maxsplit=2)
                opts['volname'] = f'Nintendo Switch NAND ({path_to_show[-2]}/{path_to_show[-1]})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = 'Nintendo Switch NAND'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=a.ro, nothreads=True, debug=a.d,
             fsname=realpath(a.image).replace(',', '_'), **opts)

    mode = 'rb' if a.ro else 'r+b'

    with open(a.keys, 'r', encoding='utf-8') as k:
        if a.split_files:
            # make sure the ending is an integer
            try:
                int(a.image[-2:])
            except ValueError:
                exit('Could not find a part number at the end of the filename.\n'
                     'A multi-part Nintendo Switch NAND backup should have filenames in the format of '
                     '"filename.bin.XX", where XX is the part number.')

            # try to find all the parts, starting with 00
            base = a.image[:-2]
            count = 0
            while True:
                if os.path.isfile(base + format(count, '02')):
                    count += 1
                else:
                    break

            if count == 0:
                exit('Could not find the first part of the multi-part backup.')

            handler = _c.SplitFileHandler((base + format(x, '02') for x in range(count)), mode)
            do_thing(handler, k, get_time(base + '00'))

        else:
            with open(a.image, mode) as f:
                do_thing(f, k, get_time(a.image))
