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
from struct import iter_unpack
from sys import exit
from typing import BinaryIO

from pyctr import crypto, ncch, util

from . import _common
from .exefs import ExeFSMount
from .romfs import RomFSMount

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ModuleNotFoundError:
    exit("fuse module not found, please install fusepy to mount images "
         "(`{} install https://github.com/billziss-gh/fusepy/archive/windows.zip`).".format(_common.pip_command))
except Exception as e:
    exit("Failed to import the fuse module:\n"
         "{}: {}".format(type(e).__name__, e))

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ModuleNotFoundError:
    exit("Cryptodome module not found, please install pycryptodomex for encryption support "
             "(`{} install pycryptodomex`).".format(_common.pip_command))
except Exception as e:
    exit("Failed to import the Cryptodome module:\n"
         "{}: {}".format(type(e).__name__, e))


class NCCHContainerMount(LoggingMixIn, Operations):
    fd = 0
    _exefs_mounted = False
    _romfs_mounted = False

    def __init__(self, ncch_fp: BinaryIO, dev: bool, g_stat: os.stat_result, seeddb: str = None):
        self.crypto = crypto.CTRCrypto(is_dev=dev)

        self.crypto.setup_keys_from_boot9()

        # get status change, modify, and file access times
        self.g_stat = {'st_ctime': int(g_stat.st_ctime), 'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        ncch_header = ncch_fp.read(0x200)
        self.ncch_reader = ncch.NCCHReader.from_header(ncch_header)

        if not self.ncch_reader.flags.no_crypto:
            # I should figure out what happens if fixed-key crypto is
            #   used along with seed. even though this will never
            #   happen in practice, I would still like to see what
            #   happens if it happens.
            if self.ncch_reader.flags.fixed_crypto_key:
                normal_key = ncch.fixed_system_key if self.ncch_reader.program_id & (0x10 << 32) else 0x0
                self.crypto.set_normal_key(0x2C, normal_key.to_bytes(0x10, 'big'))
            else:
                if self.ncch_reader.flags.uses_seed:
                    seeddb_path = ncch.check_seeddb_file(seeddb)
                    with open(seeddb_path, 'rb') as f:
                        seed = ncch.get_seed(f, self.ncch_reader.program_id)

                    self.ncch_reader.setup_seed(seed)

                self.crypto.set_keyslot('y', 0x2C, util.readbe(self.ncch_reader.get_key_y(original=True)))
                self.crypto.set_keyslot('y', self.ncch_reader.extra_keyslot,
                                        util.readbe(self.ncch_reader.get_key_y()))

        decrypted_filename = '/decrypted.' + ('cxi' if self.ncch_reader.flags.executable else 'cfa')
        self.files = {decrypted_filename: {'size': self.ncch_reader.content_size, 'offset': 0, 'enctype': 'fulldec'},
                      '/ncch.bin': {'size': 0x200, 'offset': 0, 'enctype': 'none'}}

        if self.ncch_reader.check_for_extheader():
            self.files['/extheader.bin'] = {'size': 0x800, 'offset': 0x200, 'enctype': 'normal',
                                            'keyslot': 0x2C, 'iv': (self.ncch_reader.partition_id << 64 | (0x01 << 56))}

        plain_region = self.ncch_reader.plain_region
        if plain_region.offset:
            self.files['/plain.bin'] = {'size': plain_region.size, 'offset': plain_region.offset, 'enctype': 'none'}

        logo_region = self.ncch_reader.logo_region
        if logo_region.offset:
            self.files['/logo.bin'] = {'size': logo_region.size, 'offset': logo_region.offset, 'enctype': 'none'}

        exefs_region = self.ncch_reader.exefs_region
        if exefs_region.offset:
            self.files['/exefs.bin'] = {'size': exefs_region.size, 'offset': exefs_region.offset, 'enctype': 'exefs',
                                        'keyslot': 0x2C, 'keyslot_extra': self.ncch_reader.extra_keyslot,
                                        'iv': (self.ncch_reader.partition_id << 64 | (0x02 << 56))}
            if not self.ncch_reader.flags.no_crypto:
                ncch_fp.seek(exefs_region.offset)
                exefs_header = self.crypto.aes_ctr(0x2C, self.files['/exefs.bin']['iv'], ncch_fp.read(0xA0))
                exefs_normal_ranges = [(0, 0x200)]
                for name, offset, size in iter_unpack('<8sII', exefs_header):
                    uname = name.decode('utf-8').strip('\0')
                    if uname in ('icon', 'banner'):
                        exefs_normal_ranges.append((offset + 0x200, offset + 0x200 + util.roundup(size, 0x200)))
                        self.files['/exefs.bin']['keyslot_normal_range'] = exefs_normal_ranges

            try:
                # get code compression bit
                decompress = False
                if self.ncch_reader.check_for_extheader():
                    exh_flag = self.read('/extheader.bin', 1, 0xD, 0)
                    decompress = exh_flag[0] & 1
                exefs_vfp = _common.VirtualFileWrapper(self, '/exefs.bin', exefs_region.size)
                # noinspection PyTypeChecker
                exefs_fuse = ExeFSMount(exefs_vfp, g_stat, decompress_code=decompress)
                self.exefs_fuse = exefs_fuse
                self._exefs_mounted = True
            except Exception as e:
                print("Failed to mount ExeFS: {}: {}".format(type(e).__name__, e))

        if not self.ncch_reader.flags.no_romfs:
            romfs_region = self.ncch_reader.romfs_region
            if romfs_region.offset:
                self.files['/romfs.bin'] = {'size': romfs_region.size, 'offset': romfs_region.offset,
                                            'enctype': 'normal', 'keyslot': self.ncch_reader.extra_keyslot,
                                            'iv': (self.ncch_reader.partition_id << 64 | (0x03 << 56))}

            try:
                romfs_vfp = _common.VirtualFileWrapper(self, '/romfs.bin', romfs_region.size)
                # noinspection PyTypeChecker
                romfs_fuse = RomFSMount(romfs_vfp, g_stat)
                self.romfs_fuse = romfs_fuse
                self._romfs_mounted = True
            except Exception as e:
                print("Failed to mount RomFS: {}: {}".format(type(e).__name__, e))

        self.f = ncch_fp

    def flush(self, path, fh):
        return self.f.flush()

    def getattr(self, path, fh=None):
        lpath = path.lower()
        if lpath.startswith('/exefs/'):
            return self.exefs_fuse.getattr(_common.remove_first_dir(path), fh)
        elif lpath.startswith('/romfs/'):
            return self.romfs_fuse.getattr(_common.remove_first_dir(path), fh)
        uid, gid, pid = fuse_get_context()
        if lpath == '/' or lpath == '/romfs' or lpath == '/exefs':
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        elif lpath in self.files:
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': self.files[path.lower()]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        if path.startswith('/exefs'):
            yield from self.exefs_fuse.readdir(_common.remove_first_dir(path), fh)
        elif path.startswith('/romfs'):
            yield from self.romfs_fuse.readdir(_common.remove_first_dir(path), fh)
        elif path == '/':
            yield from ('.', '..')
            yield from (x[1:] for x in self.files)
            if self._exefs_mounted:
                yield 'exefs'
            if self._romfs_mounted:
                yield 'romfs'

    def read(self, path, size, offset, fh):
        lpath = path.lower()
        if lpath.startswith('/exefs/'):
            return self.exefs_fuse.read(_common.remove_first_dir(path), size, offset, fh)
        elif lpath.startswith('/romfs/'):
            return self.romfs_fuse.read(_common.remove_first_dir(path), size, offset, fh)
        fi = self.files[lpath]
        real_offset = fi['offset'] + offset
        if fi['enctype'] == 'none' or self.ncch_reader.flags.no_crypto:
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

    def statfs(self, path):
        if path.startswith('/exefs/'):
            return self.exefs_fuse.statfs(_common.remove_first_dir(path))
        if path.startswith('/romfs/'):
            return self.romfs_fuse.statfs(_common.remove_first_dir(path))
        else:
            return {'f_bsize': 4096, 'f_blocks': self.ncch_reader.content_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                    'f_files': len(self.files)}


def main():
    parser = ArgumentParser(description="Mount Nintendo 3DS NCCH containers.",
                            parents=(_common.default_argp, _common.dev_argp, _common.seeddb_argp,
                                              _common.main_positional_args('ncch', "NCCH file")))

    a = parser.parse_args()
    opts = dict(_common.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    ncch_stat = os.stat(a.ncch)

    with open(a.ncch, 'rb') as f:
        mount = NCCHContainerMount(ncch_fp=f, dev=a.dev, g_stat=ncch_stat, seeddb=a.seeddb)
        if _common.macos or _common.windows:
            opts['fstypename'] = 'NCCH'
            if _common.macos:
                opts['volname'] = "NCCH Container ({0.product_code}; {0.program_id:016X})".format(mount.ncch_reader)
            elif _common.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = "NCCH ({0.product_code})".format(mount.ncch_reader)
        fuse = FUSE(mount, a.mount_point, foreground=a.fg or a.do, ro=True, nothreads=True,
                    fsname=os.path.realpath(a.ncch).replace(',', '_'), **opts)


if __name__ == '__main__':
    print('Note: You should be calling this script as "mount_{0}" or "{1} -mfuse3ds {0}" '
          'instead of calling it directly.'.format('ncch', _common.pip_command))
    main()
