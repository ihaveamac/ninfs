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

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ImportError:
    sys.exit('fuse module not found, please install fusepy to mount images (`pip3 install git+https://github.com/billziss-gh/fusepy.git`).')

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ImportError:
    sys.exit('Cryptodome module not found, please install pycryptodomex for encryption support (`pip3 install pycryptodomex`).')

# media unit
MU = 0x200


# since this is used often enough
def readle(b):
    return int.from_bytes(b, 'little')


# since this is used often enough
def readbe(b):
    return int.from_bytes(b, 'big')


# used from http://www.falatic.com/index.php/108/python-and-bitwise-rotation
# converted to def because pycodestyle complained to me
def rol(val, r_bits, max_bits):
    return (val << r_bits % max_bits) & (2 ** max_bits - 1) | ((val & (2 ** max_bits - 1)) >> (max_bits - (r_bits % max_bits)))


def keygen(key_x, key_y):
    return rol((rol(key_x, 2, 128) ^ key_y) + 0x1FF9E9AAC5FE0408024591DC5D52768A, 87, 128).to_bytes(0x10, 'big')


class NCCHContainer(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, ncch, dev, seeddb):
        keys_set = False
        key_x = {
            # New3DS 9.3 NCCH
            0x18: (0x82E9C9BEBFB8BDB875ECC0A07D474374, 0x304BF1468372EE64115EBD4093D84276)[dev],
            # New3DS 9.6 NCCH
            0x1B: (0x45AD04953992C7C893724A9A7BCE6182, 0x6C8B2944A0726035F941DFC018524FB6)[dev],
            # 7x NCCH
            0x25: (0xCEE7D8AB30C00DAE850EF5E382AC5AF3, 0x81907A4B6F1B47323A677974CE4AD71B)[dev],
            # Original NCCH
            0x2C: 0
        }

        # slot 0x11 is used here for fixed key (zerokey or fixed system key)
        self.normal_key = {}

        # check for boot9 to get original ncch key X
        def check_b9_file(path):
            nonlocal keys_set, key_x
            if not keys_set:
                if os.path.isfile(path):
                    key_offset = 0x59D0
                    if dev:
                        key_offset += 0x400
                    if os.path.getsize(path) == 0x10000:
                        key_offset += 0x8000
                    with open(path, 'rb') as b9:
                        b9.seek(key_offset)
                        key_x[0x2C] = int.from_bytes(b9.read(0x10), 'big')
                        key_x[0x21] = key_x[0x2C]
                    keys_set = True

        check_b9_file('boot9.bin')
        check_b9_file('boot9_prot.bin')
        check_b9_file(os.path.expanduser('~') + '/.3ds/boot9.bin')
        check_b9_file(os.path.expanduser('~') + '/.3ds/boot9_prot.bin')

        if not keys_set:
            sys.exit('Failed to get keys from boot9')

        # get status change, modify, and file access times
        ncch_stat = os.stat(ncch)
        self.g_stat = {}
        self.g_stat['st_ctime'] = int(ncch_stat.st_ctime)
        self.g_stat['st_mtime'] = int(ncch_stat.st_mtime)
        self.g_stat['st_atime'] = int(ncch_stat.st_atime)

        # open ncch and get section sizes
        self.f = open(ncch, 'rb')
        key_y = self.f.read(0x10)
        self.f.seek(0x100)
        ncch_header = self.f.read(0x100)
        if ncch_header[0:4] != b'NCCH':
            sys.exit('NCCH magic not found, is this a real NCCH container?')

        # handle flags
        ncch_flags = ncch_header[0x88:0x90]
        ncch_is_executable = ncch_flags[5] & 0x2
        self.ncch_is_decrypted = ncch_flags[7] & 0x4
        ncch_fixed_key = ncch_flags[7] & 0x1
        ncch_no_romfs = ncch_flags[7] & 0x2
        ncch_uses_seed = ncch_flags[7] & 0x20

        partition_id_raw = ncch_header[0x8:0x10]
        partition_id = readle(partition_id_raw)

        program_id_raw = ncch_header[0x18:0x20]
        program_id = readle(program_id_raw)

        ncch_normal_keyslot = 0x11 if ncch_fixed_key else 0x2C
        ncch_extra_crypto_flags = {0x00: 0x2C, 0x01: 0x25, 0x0A: 0x18, 0x0B: 0x1B}
        ncch_extra_keyslot = 0x11 if ncch_fixed_key else ncch_extra_crypto_flags[ncch_flags[3]]

        # generate keys
        if not self.ncch_is_decrypted:
            def check_seeddb_file(*files):
                for fn in files:
                    if os.path.isfile(fn):
                        return fn
                return False

            # tid is bytes in little-endian
            def get_seed(f, tid):
                f.seek(0)
                seed_count = readle(f.read(2))
                f.seek(0x10)
                for _ in range(seed_count):
                    entry = f.read(0x20)
                    if entry[0:8] == tid:
                        return entry[8:24]
                return False

            if ncch_uses_seed:
                if seeddb:
                    seeddb_name = check_seeddb_file(seeddb)
                else:
                    seeddb_name = check_seeddb_file('seeddb.bin', os.path.expanduser('~') + '/.3ds/seeddb.bin')
                if not seeddb_name:
                    sys.exit('NCCH uses seed crypto, but seeddb was not found.')

                with open(seeddb_name, 'rb') as f:
                    ncch_seed = get_seed(f, program_id_raw)
                    if not ncch_seed:
                        sys.exit('NCCH uses seed crypto, but seed was not found in seeddb.')

                    seed_verify = ncch_header[0x14:0x18]
                    seed_verify_hash = hashlib.sha256(ncch_seed + program_id_raw).digest()
                    if seed_verify != seed_verify_hash[0:4]:
                        sys.exit('NCCH uses seed crypto, but seed in seeddb failed verification.')

            if not ncch_fixed_key:
                self.normal_key[ncch_normal_keyslot] = keygen(key_x[ncch_normal_keyslot], readbe(key_y))

                if ncch_uses_seed:
                    keydata = hashlib.sha256(key_y + ncch_seed)
                    key_y = keydata.digest()[0:16]

                self.normal_key[ncch_extra_keyslot] = keygen(key_x[ncch_extra_keyslot], readbe(key_y))
            else:
                # fixed system key for certain titles, zerokey for rest
                self.normal_key[0x11] = bytes.fromhex('527CE630A9CA305F3696F3CDE954194B') if program_id & (0x10 << 32) else b'\0' * 16

        self.ncch_size = readle(ncch_header[4:8]) * 0x200

        self.files = {}
        self.files['/ncch.bin'] = {'size': 0x200, 'offset': 0, 'enctype': 'none'}

        plain_offset = readle(ncch_header[0x90:0x94])
        plain_size = readle(ncch_header[0x94:0x98])
        if plain_offset:
            self.files['/plain.bin'] = {'size': plain_size * MU, 'offset': plain_offset * MU, 'enctype': 'none'}

        logo_offset = readle(ncch_header[0x98:0x9C])
        logo_size = readle(ncch_header[0x9C:0xA0])
        if logo_offset:
            self.files['/logo.bin'] = {'size': logo_size * MU, 'offset': logo_offset * MU, 'enctype': 'none'}

        # the exh size in the header is 0x400, but the accessdesc follows it
        #   which is 0x400 too. since it isn't supposed to change size, this
        #   ignores the size and only sees if it's not 0.
        exh_size = readle(ncch_header[0x80:0x84])
        if exh_size:
            self.files['/extheader.bin'] = {'size': 0x800, 'offset': 0x200, 'enctype': 'normal', 'keyslot': ncch_normal_keyslot, 'iv': (partition_id << 64) | (0x01 << 56)}

        exefs_offset = readle(ncch_header[0xA0:0xA4])
        exefs_size = readle(ncch_header[0xA4:0xA8])
        if exefs_offset:
            self.files['/exefs.bin'] = {'size': exefs_size * MU, 'offset': exefs_offset * MU, 'enctype': 'exefs', 'keyslot': ncch_normal_keyslot, 'keyslot2': ncch_extra_keyslot}
            if not self.ncch_is_decrypted:
                exefs_iv = (partition_id << 64) | (0x02 << 56)
                cipher = AES.new(self.normal_key[ncch_normal_keyslot], AES.MODE_CTR, counter=Counter.new(128, initial_value=exefs_iv))
                self.f.seek(exefs_offset * MU)
                exefs_header = cipher.decrypt(self.f.read(0xA0))
                exefs_normal_ranges = [(0, 0x200)]
                for name, offset, size in struct.iter_unpack('<8sII', exefs_header):
                    uname = name.decode('utf-8').strip('\0')
                    if uname in ('icon', 'banner'):
                        exefs_normal_ranges.append((offset + 0x200, offset + 0x200 + (math.ceil(size / 0x200) * 0x200)))
                self.files['/exefs.bin']['iv'] = exefs_iv
                self.files['/exefs.bin']['keyslot1range'] = exefs_normal_ranges

        if not ncch_no_romfs:
            romfs_offset = readle(ncch_header[0xB0:0xB4])
            romfs_size = readle(ncch_header[0xB4:0xB8])
            if romfs_offset:
                self.files['/romfs.bin'] = {'size': romfs_size * MU, 'offset': romfs_offset * MU, 'enctype': 'normal', 'keyslot': ncch_extra_keyslot, 'iv': (partition_id << 64) | (0x03 << 56)}

    def __del__(self):
        try:
            self.f.close()
        except AttributeError:
            pass

    def access(self, path, mode):
        pass

    # unused
    def chmod(self, *args, **kwargs):
        return None

    # unused
    def chown(self, *args, **kwargs):
        return None

    def create(self, *args, **kwargs):
        self.fd += 1
        return self.fd

    def flush(self, path, fh):
        return self.f.flush()

    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        if path == '/':
            st = {'st_mode': (stat.S_IFDIR | 0o555), 'st_nlink': 2}
        elif path.lower() in self.files:
            st = {'st_mode': (stat.S_IFREG | 0o444), 'st_size': self.files[path.lower()]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(errno.ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    # unused
    def mkdir(self, *args, **kwargs):
        return None

    # unused
    def mknod(self, *args, **kwargs):
        return None

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        return ['.', '..'] + [x[1:] for x in self.files]

    def read(self, path, size, offset, fh):
        fi = self.files[path.lower()]
        real_offset = fi['offset'] + offset
        rsize = size
        if fi['enctype'] == 'none' or self.ncch_is_decrypted:
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
            counter = Counter.new(128, initial_value=iv)
            cipher = AES.new(self.normal_key[fi['keyslot']], AES.MODE_CTR, counter=counter)
            data = cipher.decrypt(data)[before:len(data) - after]

        elif fi['enctype'] == 'exefs':
            # thanks Stary2001
            before = offset % 0x200
            after = (offset + size) % 0x200
            aligned_real_offset = real_offset - before
            aligned_offset = offset - before
            aligned_size = size + before
            self.f.seek(aligned_real_offset)
            data = b''
            left = aligned_size
            for chunk in range(math.ceil(aligned_size / 0x200)):
                iv = fi['iv'] + ((aligned_offset + (chunk * 0x200)) >> 4)
                counter = Counter.new(128, initial_value=iv)
                keyslot = fi['keyslot2']
                for r in fi['keyslot1range']:
                    if r[0] <= self.f.tell() - fi['offset'] < r[1]:
                        keyslot = fi['keyslot']
                cipher = AES.new(self.normal_key[keyslot], AES.MODE_CTR, counter=counter)
                data += cipher.decrypt(self.f.read(0x200))

            data = data[before:size + before]

        return data

    # unused
    def readlink(self, *args, **kwargs):
        return None

    # unused
    def release(self, *args, **kwargs):
        return None

    # unused
    def releasedir(self, *args, **kwargs):
        return None

    # unused
    def rename(self, *args, **kwargs):
        return None

    # unused
    def rmdir(self, *args, **kwargs):
        return None

    def statfs(self, path):
        return {'f_bsize': 4096, 'f_blocks': self.ncch_size // 4096, 'f_bavail': 0, 'f_bfree': 0, 'f_files': len(self.files)}

    # unused
    def symlink(self, target, source):
        pass

    # unused
    # if this is set to None, some programs may crash.
    def truncate(self, path, length, fh=None):
        raise FuseOSError(errno.EPERM)

    # unused
    def utimens(self, *args, **kwargs):
        return None

    # unused
    def unlink(self, path):
        return None

    def write(self, path, data, offset, fh):
        raise FuseOSError(errno.EPERM)


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

    fuse = FUSE(NCCHContainer(ncch=a.ncch, dev=a.dev, seeddb=a.seeddb), a.mount_point, foreground=a.fg or a.do, fsname=os.path.realpath(a.ncch), ro=True, **opts)
