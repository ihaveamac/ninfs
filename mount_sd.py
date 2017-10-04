#!/usr/bin/env python3

import argparse
import ctypes
import errno
import hashlib
import logging
import os
import stat
import struct
import sys
from threading import Lock

windows = os.name == 'nt'
if windows:
    from ctypes import windll, wintypes

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ImportError:
    sys.exit('fuse module not found, please install fusepy to mount images (`pip3 install git+https://github.com/billziss-gh/fusepy.git`).')

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ImportError:
    sys.exit('Cryptodome module not found, please install pycryptodomex for encryption support (`pip3 install pycryptodomex`).')


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

    fd = 0

    def __init__(self, sd_dir, movable, dev, readonly=False):
        keys_set = False
        keyX = 0

        def check_b9_file(path):
            nonlocal keys_set, keyX
            if not keys_set:
                if os.path.isfile(path):
                    key_offset = 0x59F0
                    if dev:
                        key_offset += 0x400
                    if os.path.getsize(path) == 0x10000:
                        key_offset += 0x8000
                    with open(path, 'rb') as b9:
                        b9.seek(key_offset)
                        keyX = int.from_bytes(b9.read(0x10), 'big')
                    keys_set = True

        check_b9_file('boot9.bin')
        check_b9_file('boot9_prot.bin')
        check_b9_file(os.path.expanduser('~') + '/.3ds/boot9.bin')
        check_b9_file(os.path.expanduser('~') + '/.3ds/boot9_prot.bin')

        mv = open(movable, 'rb')
        mv.seek(0x110)
        keyY = mv.read(0x10)
        mv.close()
        key_hash = hashlib.sha256(keyY).digest()
        hash_parts = struct.unpack('<IIII', key_hash[0:16])
        root_dir = '{0[0]:08x}{0[1]:08x}{0[2]:08x}{0[3]:08x}'.format(hash_parts)

        if not os.path.isdir(sd_dir + '/' + root_dir):
            sys.exit('Failed to find {} in the SD dir.'.format(root_dir))

        self.key = keygen(keyX, int.from_bytes(keyY, 'big'))

        self.root = os.path.realpath(sd_dir + '/' + root_dir)
        self.root_len = len(self.root)
        self.rwlock = Lock()

    def __call__(self, op, path, *args):
        return super().__call__(op, self.root + path, *args)

    def access(self, path, mode):
        if not os.access(path, mode):
            raise FuseOSError(errno.EACCES)

    chmod = os.chmod

    def chown(self, path, *args, **kwargs):
        if not windows:
            os.chown(path, *args, **kwargs)

    def create(self, path, mode):
        if readonly:
            raise FuseOSError(errno.EPERM)
        return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)

    def flush(self, path, fh):
        if not windows:
            os.fsync(fh)

    def fsync(self, path, datasync, fh):
        if not windows:
            if datasync != 0:
                os.fdatasync(fh)
            else:
                os.fsync(fh)

    def getattr(self, path, fh=None):
        st = os.lstat(path)
        return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))

    getxattr = None

    def link(self, target, source):
        return os.link(source, target)

    listxattr = None
    mkdir = os.mkdir
    # mknod = os.mknod

    def mknod(self, path, *args, **kwargs):
        if readonly:
            raise FuseOSError(errno.EPERM)
        if not windows:
            os.mknod(path, *args, **kwargs)

    # open = os.open
    def open(self, path, *args, **kwargs):
        if windows:
            self.fd += 1
            return self.fd
        else:
            return os.open(path, *args, **kwargs)

    def read(self, path, size, offset, fh):
        # special check for special files
        if os.path.basename(path).startswith('.'):
            if windows:
                f = open(path, 'rb', buffering=0)
                f.seek(offset)
                return f.read(size)
            else:
                with self.rwlock:
                    os.lseek(fh, offset, 0)
                    return os.read(fh, size)

        before = offset % 16
        after = (offset + size) % 16
        # size_fix = size
        # if size % 16 != 0:
        #     size_fix = size + 16 - size % 16
        if windows:
            with open(path, 'rb', buffering=0) as f:
                f.seek(offset - before)
                data = f.read(size)
        else:
            with self.rwlock:
                os.lseek(fh, offset - before, 0)
                data = os.read(fh, size)
        counter = Counter.new(128, initial_value=self.path_to_iv(path) + (offset >> 4))
        cipher = AES.new(self.key, AES.MODE_CTR, counter=counter)
        out_data = cipher.decrypt(data)[before:]
        return out_data

    def readdir(self, path, fh):
        return ['.', '..'] + os.listdir(path)

    readlink = os.readlink

    def release(self, path, fh):
        if not windows:
            os.close(fh)

    def rename(self, old, new):
        raise FuseOSError(errno.EPERM)  # TODO: proper rename support
        if readonly:
            raise FuseOSError(errno.EPERM)
        return os.rename(old, self.root + new)

    rmdir = os.rmdir

    def statfs(self, path):
        if windows:
            lpSectorsPerCluster = ctypes.c_ulonglong(0)
            lpBytesPerSector = ctypes.c_ulonglong(0)
            lpNumberOfFreeClusters = ctypes.c_ulonglong(0)
            lpTotalNumberOfClusters = ctypes.c_ulonglong(0)
            ret = windll.kernel32.GetDiskFreeSpaceW(ctypes.c_wchar_p(path), ctypes.pointer(lpSectorsPerCluster), ctypes.pointer(lpBytesPerSector), ctypes.pointer(lpNumberOfFreeClusters), ctypes.pointer(lpTotalNumberOfClusters))
            if not ret:
                raise WindowsError
            free_blocks = lpNumberOfFreeClusters.value * lpSectorsPerCluster.value
            result = {'f_bavail': free_blocks,
                      'f_bfree': free_blocks,
                      'f_bsize': lpBytesPerSector.value,
                      'f_frsize': lpBytesPerSector.value,
                      'f_blocks': lpTotalNumberOfClusters.value * lpSectorsPerCluster.value,
                      'f_namemax': wintypes.MAX_PATH}
            return result
        else:
            stv = os.statvfs(path)
            # f_flag causes python interpreter crashes in some cases. i don't get it.
            return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree', 'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_frsize', 'f_namemax'))

    def symlink(self, target, source):
        return os.symlink(source, target)

    def truncate(self, path, length, fh=None):
        with open(path, 'r+b') as f:
            f.truncate(length)

    unlink = os.unlink
    utimens = os.utime

    def write(self, path, data, offset, fh):
        if readonly:
            raise FuseOSError(errno.EPERM)
        # special check for special files
        if os.path.basename(path).startswith('.'):
            if windows:
                f = open(path, 'r+b', buffering=0)
                f.seek(offset)
                return f.write(data)
            else:
                with self.rwlock:
                    os.lseek(fh, offset, 0)
                    return os.write(fh, data)

        before = offset % 16
        # after = (offset + size) % 16
        counter = Counter.new(128, initial_value=self.path_to_iv(path) + (offset >> 4))
        cipher = AES.new(self.key, AES.MODE_CTR, counter=counter)
        out_data = cipher.decrypt((b'\0' * before) + data)[before:]
        if windows:
            with open(path, 'r+b', buffering=0) as f:
                f.seek(offset - before)
                written = f.write(out_data)
        else:
            with self.rwlock:
                os.lseek(fh, offset, 0)
                written = os.write(fh, out_data)

        return written


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS SD card contents. (WRITE SUPPORT NYI)')
    parser.add_argument('--movable', metavar='MOVABLESED', help='path to movable.sed', required=True)
    parser.add_argument('--ro', help='mount read-only', action='store_true')
    parser.add_argument('--dev', help='use dev keys', action='store_const', const=1, default=0)
    parser.add_argument('--fg', help='run in foreground', action='store_true')
    parser.add_argument('--do', help='debug output (python logging module)', action='store_true')
    # parser.add_argument('--allow-rename', help='allow renaming of files (warning: files will be re-encrypted when renamed!)', action='store_true')
    parser.add_argument('-o', metavar='OPTIONS', help='mount options')
    parser.add_argument('sd_dir', help='path to folder with SD contents (on SD: /Nintendo 3DS)')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()
    try:
        opts = {o: True for o in a.o.split(',')}
    except AttributeError:
        opts = {}

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    fuse = FUSE(SDFilesystem(sd_dir=a.sd_dir, movable=a.movable, dev=a.dev, readonly=a.ro), a.mount_point, foreground=a.fg or a.do, fsname=os.path.realpath(a.sd_dir), ro=a.ro, **opts)
