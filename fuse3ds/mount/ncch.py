#!/usr/bin/env python3

"""
Mounts NCCH containers, creating a virtual filesystem of decrypted sections.
"""

import logging
import os
from argparse import ArgumentParser
from collections import OrderedDict
from errno import ENOENT
from math import ceil
from stat import S_IFDIR, S_IFREG
from sys import exit, argv
from typing import BinaryIO, Dict

from pyctr.crypto import CTRCrypto
from pyctr.types.ncch import NCCHReader, FIXED_SYSTEM_KEY
from pyctr.util import readbe, roundup

from . import _common as _c
from .exefs import ExeFSMount
from .romfs import RomFSMount

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ModuleNotFoundError:
    exit("fuse module not found, please install fusepy to mount images "
         "(`{} -mpip install https://github.com/billziss-gh/fusepy/archive/windows.zip`).".format(_c.python_cmd))
except Exception as e:
    exit("Failed to import the fuse module:\n"
         "{}: {}".format(type(e).__name__, e))

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ModuleNotFoundError:
    exit("Cryptodome module not found, please install pycryptodomex for encryption support "
         "(`{} install pycryptodomex`).".format(_c.python_cmd))
except Exception as e:
    exit("Failed to import the Cryptodome module:\n"
         "{}: {}".format(type(e).__name__, e))


class NCCHContainerMount(LoggingMixIn, Operations):
    fd = 0
    _exefs_mounted = False
    _romfs_mounted = False
    romfs_fuse = None
    exefs_fuse = None

    def __init__(self, ncch_fp: BinaryIO, g_stat: os.stat_result, decompress_code: bool = True, dev: bool = False,
                 seeddb: str = None):
        self.crypto = CTRCrypto(is_dev=dev)

        self.decompress_code = decompress_code
        self.seeddb = seeddb
        self.files = {}  # type: Dict[str, Dict]

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
                self.crypto.set_normal_key(0x2C, normal_key.to_bytes(0x10, 'big'))
            else:
                if self.reader.flags.uses_seed:
                    self.reader.load_seed_from_seeddb()

                self.crypto.set_keyslot('y', 0x2C, readbe(self.reader.get_key_y(original=True)))
                self.crypto.set_keyslot('y', self.reader.extra_keyslot,
                                        readbe(self.reader.get_key_y()))

    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass

    destroy = __del__

    def init(self, path):
        decrypted_filename = '/decrypted.' + ('cxi' if self.reader.flags.executable else 'cfa')

        self.files[decrypted_filename] =  {'size': self.reader.content_size, 'offset': 0, 'enctype': 'fulldec'}
        self.files['/ncch.bin'] = {'size': 0x200, 'offset': 0, 'enctype': 'none'}

        if self.reader.check_for_extheader():
            self.files['/extheader.bin'] = {'size': 0x800, 'offset': 0x200, 'enctype': 'normal',
                                            'keyslot': 0x2C, 'iv': (self.reader.partition_id << 64 | (0x01 << 56))}

        plain_region = self.reader.plain_region
        if plain_region.offset:
            self.files['/plain.bin'] = {'size': plain_region.size, 'offset': plain_region.offset, 'enctype': 'none'}

        logo_region = self.reader.logo_region
        if logo_region.offset:
            self.files['/logo.bin'] = {'size': logo_region.size, 'offset': logo_region.offset, 'enctype': 'none'}

        exefs_region = self.reader.exefs_region
        if exefs_region.offset:
            self.files['/exefs.bin'] = {'size': exefs_region.size, 'offset': exefs_region.offset, 'enctype': 'exefs',
                                        'keyslot': 0x2C, 'keyslot_extra': self.reader.extra_keyslot,
                                        'iv': (self.reader.partition_id << 64 | (0x02 << 56)),
                                        'keyslot_normal_range': [(0, 0x200)]}

            try:
                # get code compression bit
                decompress = False
                if self.decompress_code and self.reader.check_for_extheader():
                    exh_flag = self.read('/extheader.bin', 1, 0xD, 0)
                    decompress = exh_flag[0] & 1
                exefs_vfp = _c.VirtualFileWrapper(self, '/exefs.bin', exefs_region.size)
                # noinspection PyTypeChecker
                exefs_fuse = ExeFSMount(exefs_vfp, self._g_stat, decompress_code=decompress, strict=True)
                exefs_fuse.init(path)
                self.exefs_fuse = exefs_fuse
            except Exception as e:
                print("Failed to mount ExeFS: {}: {}".format(type(e).__name__, e))
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

            try:
                romfs_vfp = _c.VirtualFileWrapper(self, '/romfs.bin', romfs_region.size)
                # noinspection PyTypeChecker
                romfs_fuse = RomFSMount(romfs_vfp, self._g_stat)
                romfs_fuse.init(path)
                self.romfs_fuse = romfs_fuse
            except Exception as e:
                print("Failed to mount RomFS: {}: {}".format(type(e).__name__, e))

    def flush(self, path, fh):
        return self.f.flush()

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        if path.startswith('/exefs/'):
            return self.exefs_fuse.getattr(_c.remove_first_dir(path), fh)
        elif path.startswith('/romfs/'):
            return self.romfs_fuse.getattr(_c.remove_first_dir(path), fh)
        uid, gid, pid = fuse_get_context()
        if path == '/' or path == '/romfs' or path == '/exefs':
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
            data = self.crypto.aes_ctr(fi['keyslot'], iv, data)[before:size + before]

        elif fi['enctype'] == 'exefs':
            # thanks Stary2001
            before = offset % 0x200
            aligned_real_offset = real_offset - before
            aligned_offset = offset - before
            aligned_size = size + before
            self.f.seek(aligned_real_offset)
            data = b''
            for chunk in range(ceil(aligned_size / 0x200)):
                iv = fi['iv'] + ((aligned_offset + (chunk * 0x200)) >> 4)
                keyslot = fi['keyslot_extra']
                for r in fi['keyslot_normal_range']:
                    if r[0] <= self.f.tell() - fi['offset'] < r[1]:
                        keyslot = fi['keyslot']
                data += self.crypto.aes_ctr(keyslot, iv, self.f.read(0x200))

            data = data[before:size + before]

        elif fi['enctype'] == 'fulldec':
            # this could be optimized much better
            before = offset % 0x200
            aligned_real_offset = real_offset - before
            aligned_offset = offset - before
            aligned_size = size + before
            self.f.seek(aligned_real_offset)
            data = b''
            files_to_read = OrderedDict()
            for chunk in range(ceil(aligned_size / 0x200)):
                new_offset = (aligned_offset + (chunk * 0x200))
                added = False
                for fname, attrs in self.files.items():
                    if attrs['enctype'] == 'fulldec':
                        continue
                    if attrs['offset'] <= new_offset < attrs['offset'] + attrs['size']:
                        if fname not in files_to_read:
                            files_to_read[fname] = [new_offset - attrs['offset'], 0]
                        files_to_read[fname][1] += 0x200
                        added = True
                if not added:
                    files_to_read['raw{}'.format(chunk)] = [new_offset, 0x200]

            for fname, info in files_to_read.items():
                try:
                    new_data = self.read(fname, info[1], info[0], 0)
                    if fname == '/ncch.bin':
                        # fix crypto flags
                        ncch_array = bytearray(new_data)
                        ncch_array[0x18B] = 0
                        ncch_array[0x18F] = 4
                        new_data = bytes(ncch_array)
                except KeyError:
                    # for unknown files
                    self.f.seek(info[0])
                    new_data = self.f.read(info[1])

                data += new_data

            data = data[before:size + before]

        else:
            from pprint import pformat
            print('--------------------------------------------------',
                  'Warning: unknown file type (this should not happen!)',
                  'Please file an issue or contact the developer with the details below.',
                  '  https://github.com/ihaveamac/fuse-3ds/issues',
                  '--------------------------------------------------',
                  '{!r}: {!r}'.format(path, pformat(fi)), sep='\n')

            data = b'g' * size

        return data

    @_c.ensure_lower_path
    def statfs(self, path):
        if path.startswith('/exefs/'):
            return self.exefs_fuse.statfs(_c.remove_first_dir(path))
        if path.startswith('/romfs/'):
            return self.romfs_fuse.statfs(_c.remove_first_dir(path))
        else:
            return {'f_bsize': 4096, 'f_blocks': self.reader.content_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                    'f_files': len(self.files)}


def main(prog: str = None, args: list = None):
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description="Mount Nintendo 3DS NCCH containers.",
                            parents=(_c.default_argp, _c.dev_argp, _c.seeddb_argp,
                                     _c.main_positional_args('ncch', "NCCH file")))

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    ncch_stat = os.stat(a.ncch)

    with open(a.ncch, 'rb') as f:
        mount = NCCHContainerMount(ncch_fp=f, dev=a.dev, g_stat=ncch_stat, seeddb=a.seeddb)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'NCCH'
            if _c.macos:
                opts['volname'] = "NCCH Container ({0.product_code}; {0.program_id:016X})".format(mount.reader)
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = "NCCH ({0.product_code})".format(mount.reader)
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=os.path.realpath(a.ncch).replace(',', '_'), **opts)


if __name__ == '__main__':
    print('Note: You should be calling this script as "mount_{0}" or "{1} -mfuse3ds {0}" '
          'instead of calling it directly.'.format('ncch', _c.python_cmd))
    main()
