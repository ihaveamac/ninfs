# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts NCCH containers, creating a virtual filesystem of decrypted sections.
"""

import logging
import os
from errno import ENOENT
from math import ceil
from stat import S_IFDIR, S_IFREG
from sys import argv
from threading import Thread
from typing import BinaryIO, TYPE_CHECKING

from pyctr.crypto import CryptoEngine, Keyslot
from pyctr.types.ncch import NCCHReader, FIXED_SYSTEM_KEY
from pyctr.util import readbe, roundup
from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
from .exefs import ExeFSMount
from .romfs import RomFSMount

if TYPE_CHECKING:
    from typing import Dict, List


class NCCHContainerMount(LoggingMixIn, Operations):
    fd = 0
    romfs_fuse = None
    exefs_fuse = None

    def __init__(self, ncch_fp: BinaryIO, g_stat: os.stat_result, decompress_code: bool = True, dev: bool = False,
                 seeddb: str = None):
        self.crypto = CryptoEngine(dev=dev)

        self.decompress_code = decompress_code
        self.seeddb = seeddb
        self.files: Dict[str, Dict] = {}

        # get status change, modify, and file access times
        self._g_stat = g_stat
        self.g_stat = {'st_ctime': int(g_stat.st_ctime), 'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        ncch_header = ncch_fp.read(0x200)
        self.reader = NCCHReader.from_header(ncch_header)

        self.f = ncch_fp

        if not self.reader.flags.no_crypto:
            # I should figure out what happens if fixed-key crypto is
            #   used along with seed. even though this will never
            #   happen in practice, I would still like to see what
            #   happens if it happens.
            if self.reader.flags.fixed_crypto_key:
                normal_key = FIXED_SYSTEM_KEY if self.reader.program_id & (0x10 << 32) else 0x0
                self.crypto.set_normal_key(Keyslot.NCCH, normal_key.to_bytes(0x10, 'big'))
            else:
                if self.reader.flags.uses_seed:
                    self.reader.load_seed_from_seeddb()

                self.crypto.set_keyslot('y', Keyslot.NCCH, readbe(self.reader.get_key_y(original=True)))
                self.crypto.set_keyslot('y', self.reader.extra_keyslot,
                                        readbe(self.reader.get_key_y()))

    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass

    destroy = __del__

    def init(self, path, _setup_romfs=True):
        decrypted_filename = '/decrypted.' + ('cxi' if self.reader.flags.executable else 'cfa')

        self.files[decrypted_filename] = {'size': self.reader.content_size, 'offset': 0, 'enctype': 'fulldec'}
        self.files['/ncch.bin'] = {'size': 0x200, 'offset': 0, 'enctype': 'none'}

        if self.reader.check_for_extheader():
            self.files['/extheader.bin'] = {'size': 0x800, 'offset': 0x200, 'enctype': 'normal',
                                            'keyslot': Keyslot.NCCH,
                                            'iv': (self.reader.partition_id << 64 | (0x01 << 56))}

        plain_region = self.reader.plain_region
        if plain_region.offset:
            self.files['/plain.bin'] = {'size': plain_region.size, 'offset': plain_region.offset, 'enctype': 'none'}

        logo_region = self.reader.logo_region
        if logo_region.offset:
            self.files['/logo.bin'] = {'size': logo_region.size, 'offset': logo_region.offset, 'enctype': 'none'}

        exefs_region = self.reader.exefs_region
        if exefs_region.offset:
            exefs_type = 'exefs'
            if self.reader.extra_keyslot == Keyslot.NCCH:
                exefs_type = 'normal'
            self.files['/exefs.bin'] = {'size': exefs_region.size, 'offset': exefs_region.offset, 'enctype': exefs_type,
                                        'keyslot': Keyslot.NCCH, 'keyslot_extra': self.reader.extra_keyslot,
                                        'iv': (self.reader.partition_id << 64 | (0x02 << 56)),
                                        'keyslot_normal_range': [(0, 0x200)]}

            # noinspection PyBroadException
            try:
                # get code compression bit
                decompress = False
                if self.decompress_code and self.reader.check_for_extheader():
                    exh_flag = self.read('/extheader.bin', 1, 0xD, 0)
                    decompress = exh_flag[0] & 1
                exefs_vfp = _c.VirtualFileWrapper(self, '/exefs.bin', exefs_region.size)
                exefs_fuse = ExeFSMount(exefs_vfp, self._g_stat, decompress_code=decompress, strict=True)
                self.exefs_fuse = exefs_fuse
            except Exception as e:
                print(f'Failed to mount ExeFS: {type(e).__name__}: {e}')
                self.exefs_fuse = None
            else:
                if not self.reader.flags.no_crypto:
                    for n, ent in self.exefs_fuse.reader.entries.items():
                        if n in {'icon', 'banner'}:
                            self.files['/exefs.bin']['keyslot_normal_range'].append(
                                (ent.offset + 0x200, ent.offset + 0x200 + roundup(ent.size, 0x200)))

        if not self.reader.flags.no_romfs:
            romfs_region = self.reader.romfs_region
            if romfs_region.offset:
                self.files['/romfs.bin'] = {'size': romfs_region.size, 'offset': romfs_region.offset,
                                            'enctype': 'normal', 'keyslot': self.reader.extra_keyslot,
                                            'iv': (self.reader.partition_id << 64 | (0x03 << 56))}

        if _setup_romfs:
            self.setup_romfs()

        if self.exefs_fuse and '/code.bin' in self.exefs_fuse.files:
            if self.exefs_fuse.decompress_code:
                # the data is read here to avoid an issue with threading
                # (yes i am kind of lazy)
                print('ExeFS: Reading .code...')
                data = self.exefs_fuse.read('/code.bin', self.exefs_fuse.files['/code.bin'].size, 0, 0)
            else:
                data = None
            Thread(target=self.exefs_fuse.init, daemon=True, args=(path, data)).start()

    def setup_romfs(self):
        if '/romfs.bin' in self.files:
            # noinspection PyBroadException
            try:
                romfs_vfp = _c.VirtualFileWrapper(self, '/romfs.bin', self.reader.romfs_region.size)
                # noinspection PyTypeChecker
                romfs_fuse = RomFSMount(romfs_vfp, self._g_stat)
                romfs_fuse.init('/')
                self.romfs_fuse = romfs_fuse
            except Exception as e:
                print(f'Failed to mount RomFS: {type(e).__name__}: {e}')

    def flush(self, path, fh):
        return self.f.flush()

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
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': self.files[path]['size'], 'st_nlink': 1}
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
        fi = self.files[path]
        real_offset = fi['offset'] + offset
        if fi['offset'] + offset > fi['offset'] + fi['size']:
            return b''
        if offset + size > fi['size']:
            size = fi['size'] - offset

        if fi['enctype'] == 'none' or self.reader.flags.no_crypto:
            # if no encryption, just read and return
            self.f.seek(real_offset)
            data = self.f.read(size)

        elif fi['enctype'] == 'normal':
            self.f.seek(real_offset)
            data = self.f.read(size)
            # thanks Stary2001
            before = offset % 16
            after = (offset + size) % 16
            data = (b'\0' * before) + data + (b'\0' * after)
            iv = fi['iv'] + (offset >> 4)
            data = self.crypto.create_ctr_cipher(fi['keyslot'], iv).decrypt(data)[before:size + before]

        elif fi['enctype'] == 'exefs':
            # thanks Stary2001
            before = offset % 0x200
            aligned_real_offset = real_offset - before
            aligned_offset = offset - before
            aligned_size = size + before
            self.f.seek(aligned_real_offset)

            def do_thing(al_offset: int, al_size: int, cut_start: int, cut_end: int):
                end: int = al_offset + (ceil(al_size / 0x200) * 0x200)
                last_chunk_offset = end - 0x200
                # noinspection PyTypeChecker
                for chunk in range(al_offset, end, 0x200):
                    iv = fi['iv'] + (chunk >> 4)
                    keyslot = fi['keyslot_extra']
                    for r in fi['keyslot_normal_range']:
                        if r[0] <= self.f.tell() - fi['offset'] < r[1]:
                            keyslot = fi['keyslot']
                    out = self.crypto.create_ctr_cipher(keyslot, iv).decrypt(self.f.read(0x200))
                    if chunk == al_offset:
                        out = out[cut_start:]
                    if chunk == last_chunk_offset and cut_end != 0x200:
                        out = out[:-cut_end]
                    yield out

            data = b''.join(do_thing(aligned_offset, aligned_size, before, 0x200 - ((size + before) % 0x200)))

        elif fi['enctype'] == 'fulldec':
            # this could be optimized much better
            before = offset % 0x200
            aligned_real_offset = real_offset - before
            aligned_offset = offset - before
            aligned_size = size + before
            self.f.seek(aligned_real_offset)

            def do_thing(al_offset: int, al_size: int, cut_start: int, cut_end: int):
                end: int = al_offset + (ceil(al_size / 0x200) * 0x200)
                # dict is ordered by default in CPython since 3.6.0
                # and part of the language spec since 3.7.0
                to_read: Dict[str, List[int]] = {}

                if self.reader.check_for_extheader():
                    extheader_start = 0x200
                    extheader_end = 0xA00
                else:
                    extheader_start = extheader_end = 0

                logo = self.reader.logo_region
                logo_start = logo.offset
                logo_end = logo_start + logo.size

                plain = self.reader.plain_region
                plain_start = plain.offset
                plain_end = plain_start + plain.size

                exefs = self.reader.exefs_region
                exefs_start = exefs.offset
                exefs_end = exefs_start + exefs.size

                romfs = self.reader.romfs_region
                romfs_start = romfs.offset
                romfs_end = romfs_start + romfs.size

                for chunk_offset in range(al_offset, end, 0x200):
                    # RomFS check first, since it might be faster
                    if romfs_start <= chunk_offset < romfs_end:
                        name = '/romfs.bin'
                        curr_offset = romfs_start
                    # ExeFS check second, since it might be faster
                    elif exefs_start <= chunk_offset < exefs_end:
                        name = '/exefs.bin'
                        curr_offset = exefs_start
                    # NCCH check, always 0x0 to 0x200
                    elif 0 <= chunk_offset < 0x200:
                        name = '/ncch.bin'
                        curr_offset = 0
                    elif extheader_start <= chunk_offset < extheader_end:
                        name = '/extheader.bin'
                        curr_offset = extheader_start
                    elif logo_start <= chunk_offset < logo_end:
                        name = '/logo.bin'
                        curr_offset = logo_start
                    elif plain_start <= chunk_offset < plain_end:
                        name = '/plain.bin'
                        curr_offset = plain_start
                    else:
                        name = f'raw{chunk_offset}'
                        curr_offset = 0
                    if name not in to_read:
                        to_read[name] = [chunk_offset - curr_offset, 0]
                    to_read[name][1] += 0x200
                    last_name = name

                is_start = True
                for name, info in to_read.items():
                    try:
                        new_data = self.read(name, info[1], info[0], 0)
                        if name == '/ncch.bin':
                            # fix crypto flags
                            ncch_array = bytearray(new_data)
                            ncch_array[0x18B] = 0
                            ncch_array[0x18F] = 4
                            new_data = bytes(ncch_array)
                    except KeyError:
                        # for unknown files
                        self.f.seek(info[0])
                        new_data = self.f.read(info[1])
                    if is_start is True:
                        new_data = new_data[cut_start:]
                        is_start = False
                    # noinspection PyUnboundLocalVariable
                    if name == last_name and cut_end != 0x200:
                        new_data = new_data[:-cut_end]

                    yield new_data

            data = b''.join(do_thing(aligned_offset, aligned_size, before, 0x200 - ((size + before) % 0x200)))

        else:
            from pprint import pformat
            print('--------------------------------------------------',
                  'Warning: unknown file type (this should not happen!)',
                  'Please file an issue or contact the developer with the details below.',
                  '  https://github.com/ihaveamac/ninfs/issues',
                  '--------------------------------------------------',
                  f'{path!r}: {pformat(fi)!r}', sep='\n')

            data = b'g' * size

        return data

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
                            parents=(_c.default_argp, _c.dev_argp, _c.seeddb_argp,
                                     _c.main_args('ncch', 'NCCH file')))

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    ncch_stat = os.stat(a.ncch)

    with open(a.ncch, 'rb') as f:
        mount = NCCHContainerMount(ncch_fp=f, dev=a.dev, g_stat=ncch_stat, seeddb=a.seeddb)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'NCCH'
            if _c.macos:
                opts['volname'] = f'NCCH Container ({mount.reader.product_code}; {mount.reader.program_id:016X})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = f'NCCH ({mount.reader.product_code})'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=os.path.realpath(a.ncch).replace(',', '_'), **opts)
