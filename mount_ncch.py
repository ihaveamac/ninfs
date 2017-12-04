#!/usr/bin/env python3

import argparse
import errno
import hashlib
import logging
import math
import os
import stat
import struct
import sys

from pyctr import crypto, ncch, romfs, util

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ImportError:
    sys.exit('fuse module not found, please install fusepy to mount images '
             '(`pip3 install git+https://github.com/billziss-gh/fusepy.git`).')

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ImportError:
    sys.exit('Cryptodome module not found, please install pycryptodomex for encryption support '
             '(`pip3 install pycryptodomex`).')


class NCCHContainerMount(LoggingMixIn, Operations):
    fd = 0
    _romfs_mounted = False

    def __init__(self, ncch_file, dev, seeddb=None):
        self.crypto = crypto.CTRCrypto(is_dev=dev)

        self.crypto.setup_keys_from_boot9()

        # get status change, modify, and file access times
        ncch_stat = os.stat(ncch_file)
        self.g_stat = {'st_ctime': int(ncch_stat.st_ctime), 'st_mtime': int(ncch_stat.st_mtime),
                       'st_atime': int(ncch_stat.st_atime)}

        self.f = open(ncch_file, 'rb')
        ncch_header = self.f.read(0x200)
        self.ncch_reader = ncch.NCCHReader.from_header(ncch_header)

        if not self.ncch_reader.flags.no_crypto:
            # I should figure out what happens if fixed-key crypto is
            #   used along with seed. even though this will never
            #   happen in practice, I would still like to see what
            #   happens if it happens.
            if self.ncch_reader.flags.fixed_crypto_key:
                normal_key = ncch.fixed_system_key if self.ncch_reader.program_id & (0x10 << 32) else 0x0
                self.crypto.set_normal_key(0x2C, normal_key)
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
                self.f.seek(exefs_region.offset)
                exefs_header = self.crypto.aes_ctr(0x2C, self.files['/exefs.bin']['iv'], self.f.read(0xA0))
                exefs_normal_ranges = [(0, 0x200)]
                for name, offset, size in struct.iter_unpack('<8sII', exefs_header):
                    uname = name.decode('utf-8').strip('\0')
                    if uname in ('icon', 'banner'):
                        exefs_normal_ranges.append((offset + 0x200, offset + 0x200 + util.roundup(size, 0x200)))
                        self.files['/exefs.bin']['keyslot_normal_range'] = exefs_normal_ranges

        if not self.ncch_reader.flags.no_romfs:
            romfs_region = self.ncch_reader.romfs_region
            if romfs_region.offset:
                self.files['/romfs.bin'] = {'size': romfs_region.size, 'offset': romfs_region.offset,
                                            'enctype': 'normal', 'keyslot': self.ncch_reader.extra_keyslot,
                                            'iv': (self.ncch_reader.partition_id << 64 | (0x03 << 56))}

            # try:
            #     ivfc_header = self.read('/romfs.bin', romfs.IVFC_HEADER_SIZE, 0, 0)
            #     lv3_offset = romfs.get_lv3_offset_from_ivfc(ivfc_header)
            #     lv3_header = self.read('/romfs.bin', romfs.ROMFS_LV3_HEADER_SIZE, lv3_offset, 0)
            #     romfs_reader = romfs.RomFSReader.from_lv3_header(lv3_header)
            #     dirmeta_region = romfs_reader.dirmeta_region
            #     filemeta_region = romfs_reader.filemeta_region
            #     filedata_offset = romfs_reader.filedata_offset
            #     dirmeta = self.read('/romfs.bin', dirmeta_region.size, dirmeta_region.offset + lv3_offset, 0)
            #     filemeta = self.read('/romfs.bin', filemeta_region.size, filemeta_region.offset + lv3_offset, 0)
            #     romfs_reader.parse_metadata(dirmeta, filemeta)
            #
            #     self.romfs_reader = romfs_reader
            #     self.lv3_offset = lv3_offset
            #     self._romfs_mounted = True
            #
            # except Exception as e:
            #     print("failed to mount RomFS: {}: {}".format(type(e).__name__, e))

    def __del__(self):
        try:
            self.f.close()
        except AttributeError:
            pass

    def flush(self, path, fh):
        return self.f.flush()

    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        if path == '/' or path.lower() == '/romfs':
            st = {'st_mode': (stat.S_IFDIR | 0o555), 'st_nlink': 2}
        elif path.lower() in self.files:
            st = {'st_mode': (stat.S_IFREG | 0o444), 'st_size': self.files[path.lower()]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(errno.ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        out = ['.', '..']
        # if path.lower().startswith('/romfs/'):
        #
        # if self._romfs_mounted:
        return out + [x[1:] for x in self.files]

    def read(self, path, size, offset, fh):
        if path.lower().startswith('/romfs/'):
            pass

        fi = self.files[path.lower()]
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
            for chunk in range(math.ceil(aligned_size / 0x200)):
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
            for chunk in range(math.ceil(aligned_size / 0x200)):
                new_offset = (aligned_offset + (chunk * 0x200))
                new_data = b''
                for fname, attrs in self.files.items():
                    if attrs['enctype'] == 'fulldec':
                        continue
                    if attrs['offset'] <= new_offset < attrs['offset'] + attrs['size']:
                        new_data = self.read(fname, 0x200, new_offset - attrs['offset'], 0)
                        if fname == '/ncch.bin':
                            # fix crypto flags
                            ncch_array = bytearray(new_data)
                            ncch_array[0x18B] = 0
                            ncch_array[0x18F] = 4
                            new_data = bytes(ncch_array)
                if not new_data:
                    self.f.seek(new_offset)
                    new_data = self.f.read(0x200)

                data += new_data

            data = data[before:size + before]

        return data

    def statfs(self, path):
        return {'f_bsize': 4096, 'f_blocks': self.ncch_reader.content_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS NCCH containers.')
    parser.add_argument('--dev', help='use dev keys', action='store_const', const=1, default=0)
    parser.add_argument('--seeddb', help='path to seeddb.bin')
    parser.add_argument('--fg', '-f', help='run in foreground', action='store_true')
    parser.add_argument('--do', help='debug output (python logging module)', action='store_true')
    parser.add_argument('-o', metavar='OPTIONS', help='mount options')
    parser.add_argument('ncch', help='NCCH file')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()
    try:
        opts = {o: True for o in a.o.split(',')}
    except AttributeError:
        opts = {}

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    fuse = FUSE(NCCHContainerMount(ncch_file=a.ncch, dev=a.dev, seeddb=a.seeddb), a.mount_point, foreground=a.fg or a.do,
                fsname=os.path.realpath(a.ncch), ro=True, nothreads=True, **opts)
