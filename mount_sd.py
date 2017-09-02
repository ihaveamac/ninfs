#!/usr/bin/env python3

import argparse
import errno
import hashlib
import logging
import os
import stat
import struct
import sys
from threading import Lock

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
except ImportError:
    sys.exit('fuse module not found, please install fusepy to mount images (`pip install fusepy`).')

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ImportError:
    sys.exit('Cryptodome module not found, please install pycryptodomex for encryption support (`pip install pycryptodomex`).')

# 0x34 KeyX must be hardcoded here at the moment. I didn't have time to add
#   code to read from b9 but I wanted to get this up when it was working.
KEYX = 0x00000000000000000000000000000000


# used from http://www.falatic.com/index.php/108/python-and-bitwise-rotation
# converted to def because pycodestyle complained to me
def rol(val, r_bits, max_bits):
    return (val << r_bits % max_bits) & (2 ** max_bits - 1) | ((val & (2 ** max_bits - 1)) >> (max_bits - (r_bits % max_bits)))


def keygen(key_x, key_y):
    return rol((rol(key_x, 2, 128) ^ key_y) + 0x1FF9E9AAC5FE0408024591DC5D52768A, 87, 128).to_bytes(0x10, 'big')


class SDFilesystem(LoggingMixIn, Operations):
    def path_to_iv(self, path):
        path_hash = hashlib.sha256(path[self.root_len + 33:].lower().encode('utf-16le') + b'\0\0').digest()
        hash_p1 = int.from_bytes(path_hash[0:16], 'big')
        hash_p2 = int.from_bytes(path_hash[16:32], 'big')
        return hash_p1 ^ hash_p2

    def __init__(self):
        mv = open(a.movable, 'rb')
        mv.seek(0x110)
        keyY = mv.read(0x10)
        mv.close()
        key_hash = hashlib.sha256(keyY).digest()
        hash_parts = struct.unpack('<IIII', key_hash[0:16])
        root_dir = '{0[0]:08x}{0[1]:08x}{0[2]:08x}{0[3]:08x}'.format(hash_parts)

        print(a.sd_dir + '/' + root_dir)

        self.key = keygen(KEYX, int.from_bytes(keyY, 'big'))

        self.root = os.path.realpath(a.sd_dir + '/' + root_dir)
        self.root_len = len(self.root)
        self.rwlock = Lock()

    def __call__(self, op, path, *args):
        return super().__call__(op, self.root + path, *args)

    def access(self, path, mode):
        if not os.access(path, mode):
            raise FuseOSError(errno.EACCES)

    chmod = os.chmod
    chown = os.chown

    def create(self, path, mode):
        return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)

    def flush(self, path, fh):
        return os.fsync(fh)

    def fsync(self, path, datasync, fh):
        if datasync != 0:
            return os.fdatasync(fh)
        else:
            return os.fsync(fh)

    def getattr(self, path, fh=None):
        st = os.lstat(path)
        return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
            'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))

    getxattr = None

    def link(self, target, source):
        return os.link(source, target)

    listxattr = None
    mkdir = os.mkdir
    mknod = os.mknod
    open = os.open

    def read(self, path, size, offset, fh):
        before = offset % 16
        after = (offset + size) % 16
        if size % 16 != 0:
            size = size + 16 - size % 16
        with self.rwlock:
            os.lseek(fh, offset - before, 0)
            data = os.read(fh, size)
            counter = Counter.new(128, initial_value=self.path_to_iv(path) + (offset >> 4))
            cipher = AES.new(self.key, AES.MODE_CTR, counter=counter)
            return cipher.decrypt(data)[before:len(data) - after]

    def readdir(self, path, fh):
        return ['.', '..'] + os.listdir(path)

    readlink = os.readlink

    def release(self, path, fh):
        return os.close(fh)

    def rename(self, old, new):
        return os.rename(old, self.root + new)

    rmdir = os.rmdir

    def statfs(self, path):
        stv = os.statvfs(path)
        # f_flag causes python interpreter crashes in some cases. i don't get it.
        return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree',
            'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files',  # 'f_flag',
            'f_frsize', 'f_namemax'))

    def symlink(self, target, source):
        return os.symlink(source, target)

    def truncate(self, path, length, fh=None):
        with open(path, 'r+') as f:
            f.truncate(length)

    unlink = os.unlink
    utimens = os.utime

    def write(self, path, data, offset, fh):
        with self.rwlock:
            os.lseek(fh, offset, 0)
            return os.write(fh, data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS SD card contents. (WRITE SUPPORT NYI)')
    parser.add_argument('--movable', metavar='MOVABLESED', help='path to movable.sed', required=True)
    parser.add_argument('--ro', help='mount read-only', action='store_true')
    parser.add_argument('--dev', help='use dev keys', action='store_const', const=1, default=0)
    parser.add_argument('--fg', help='run in foreground', action='store_true')
    parser.add_argument('sd_dir', help='path to folder with SD contents (on SD: /Nintendo 3DS)')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()

    # logging.basicConfig(level=logging.DEBUG)

    fuse = FUSE(SDFilesystem(), a.mount_point, foreground=a.fg, ro=True)
