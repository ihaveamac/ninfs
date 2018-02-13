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

import common
from pyctr import crypto, util

if common.windows:
    from ctypes import windll, wintypes

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


class SDFilesystemMount(LoggingMixIn, Operations):
    def path_to_iv(self, path):
        path_hash = hashlib.sha256(path[self.root_len + 33:].lower().encode('utf-16le') + b'\0\0').digest()
        hash_p1 = util.readbe(path_hash[0:16])
        hash_p2 = util.readbe(path_hash[16:32])
        return hash_p1 ^ hash_p2

    def __init__(self, sd_dir, movable, dev, readonly=False):
        self.fds = {}
        self.crypto = crypto.CTRCrypto(is_dev=dev)

        self.crypto.setup_keys_from_boot9()

        mv = open(movable, 'rb')
        mv.seek(0x110)
        key_y = mv.read(0x10)
        mv.close()
        key_hash = hashlib.sha256(key_y).digest()
        hash_parts = struct.unpack('<IIII', key_hash[0:16])
        self.root_dir = '{0[0]:08x}{0[1]:08x}{0[2]:08x}{0[3]:08x}'.format(hash_parts)

        if not os.path.isdir(sd_dir + '/' + self.root_dir):
            sys.exit('Failed to find {} in the SD dir.'.format(self.root_dir))

        print('Root dir: ' + self.root_dir)

        self.crypto.set_keyslot('y', 0x34, util.readbe(key_y))
        print('Key:      ' + self.crypto.key_normal[0x34].hex())

        self.root = os.path.realpath(sd_dir + '/' + self.root_dir)
        self.root_len = len(self.root)
        self.rwlock = Lock()

        self.readonly = readonly

    # noinspection PyMethodOverriding
    def __call__(self, op, path, *args):
        return super().__call__(op, self.root + path, *args)

    def destroy(self, path):
        for f in self.fds.values():
            f.close()

    def access(self, path, mode):
        if not os.access(path, mode):
            raise FuseOSError(errno.EACCES)

    chmod = os.chmod

    def chown(self, path, *args, **kwargs):
        if not common.windows:
            os.chown(path, *args, **kwargs)

    def create(self, path, mode, **kwargs):
        if self.readonly:
            raise FuseOSError(errno.EROFS)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        self.fds[fd] = os.fdopen(fd, 'wb')
        return fd

    def flush(self, path, fh):
        try:
            os.fsync(fh)
        except OSError as e:
            # I am not sure why this is happening on Windows. if anyone can give me a hint, please do.
            if e.errno != errno.EBADF:  # "Bad file descriptor"
                raise
        return

    def fsync(self, path, datasync, fh):
        print('FSYNC req: {} {}'.format(datasync, fh))
        self.flush(path, fh)
        return

    def getattr(self, path, fh=None):
        st = os.lstat(path)
        uid, gid, _ = fuse_get_context()
        res = dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime', 'st_mode', 'st_mtime', 'st_nlink', 'st_size'))
        res['st_uid'] = st.st_uid if st.st_uid != 0 else uid
        res['st_gid'] = st.st_gid if st.st_gid != 0 else gid
        return res

    getxattr = None

    def link(self, target, source):
        return os.link(source, target)

    listxattr = None
    mkdir = os.mkdir
    # mknod = os.mknod

    def mknod(self, path, *args, **kwargs):
        if self.readonly:
            raise FuseOSError(errno.EROFS)
        if not common.windows:
            os.mknod(path, *args, **kwargs)

    # open = os.open
    def open(self, path, flags):
        fd = os.open(path, flags)
        mode = 'rb+'  # maybe generate the right mode? I don't think it matters
        self.fds[fd] = os.fdopen(fd, mode)
        return fd

    def read(self, path, size, offset, fh):
        f = self.fds[fh]
        # special check for special files
        if os.path.basename(path).startswith('.') or 'Nintendo DSiWare' in path:
            f.seek(offset)
            return f.read(size)

        before = offset % 16
        f.seek(offset - before)
        data = f.read(size)
        iv = self.path_to_iv(path) + (offset >> 4)
        return self.crypto.aes_ctr(0x34, iv, data)[before:]

    def readdir(self, path, fh):
        return ['.', '..'] + os.listdir(path)

    readlink = os.readlink

    def release(self, path, fh):
        self.fds[fh].close()
        del self.fds[fh]

    def rename(self, old, new):
        # TODO: proper rename support - this may not happen because there's not
        #   much reason to rename files here. copying might work since either
        #   way, the file[s] would have to be re-encrypted.
        raise FuseOSError(errno.EROFS if self.readonly else errno.EPERM)
        # if self.readonly:
        #     raise FuseOSError(errno.EROFS)
        # return os.rename(old, self.root + new)

    rmdir = os.rmdir

    def statfs(self, path):
        if common.windows:
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
            return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree', 'f_blocks', 'f_bsize', 'f_favail',
                                                             'f_ffree', 'f_files', 'f_frsize', 'f_namemax'))

    def symlink(self, target, source):
        return os.symlink(source, target)

    def truncate(self, path, length, fh=None):
        if fh is None:
            with open(path, 'r+b') as f:
                f.truncate(length)
        else:
            f = self.fds[fh]
            f.truncate(length)

    unlink = os.unlink
    utimens = os.utime

    def write(self, path, data, offset, fh):
        if self.readonly:
            raise FuseOSError(errno.EROFS)
        f = self.fds[fh]
        # special check for special files
        if os.path.basename(path).startswith('.') or 'Nintendo DSiWare' in path:
            f.seek(offset)
            return f.write(data)

        before = offset % 16
        iv = self.path_to_iv(path) + (offset >> 4)
        out_data = self.crypto.aes_ctr(0x34, iv, (b'\0' * before) + data)[before:]
        f.seek(offset)
        return f.write(out_data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS SD card contents.')
    parser.add_argument('--movable', metavar='MOVABLESED', help='path to movable.sed', required=True)
    parser.add_argument('--ro', help='mount read-only', action='store_true')
    parser.add_argument('--dev', help='use dev keys', action='store_const', const=1, default=0)
    parser.add_argument('--fg', help='run in foreground', action='store_true')
    parser.add_argument('--do', help='debug output (python logging module)', action='store_true')
    # parser.add_argument('--allow-rename', help='allow renaming of files (warning: files will be re-encrypted '
    #                                            'when renamed!)', action='store_true')
    parser.add_argument('-o', metavar='OPTIONS', help='mount options')
    parser.add_argument('sd_dir', help='path to folder with SD contents (on SD: /Nintendo 3DS)')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()
    opts = dict(common.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    mount = SDFilesystemMount(sd_dir=a.sd_dir, movable=a.movable, dev=a.dev, readonly=a.ro)
    if common.macos or common.windows:
        opts['fstypename'] = 'SDCARD'
        if common.macos:
            opts['volname'] = "Nintendo 3DS SD Card ({})".format(mount.root_dir)
        else:
            # windows
            opts['volname'] = "Nintendo 3DS SD Card ({}…)".format(mount.root_dir[0:8])
            opts['case_insensitive'] = False
    fuse = FUSE(mount, a.mount_point, foreground=a.fg or a.do, ro=a.ro, nothreads=True,
                fsname=os.path.realpath(a.sd_dir).replace(',', '_'), **opts)
