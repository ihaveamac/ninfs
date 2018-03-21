#!/usr/bin/env python3

"""
Mounts SD contents under `/Nintendo 3DS`, creating a virtual filesystem with decrypted contents. movable.sed required.
"""

import logging
import os
from argparse import ArgumentParser
from ctypes import c_wchar_p, pointer, c_ulonglong
from errno import EPERM, EACCES, EROFS, EBADF
from hashlib import sha256
from struct import unpack
from sys import exit

from pyctr import crypto, util

from . import _common

if _common.windows:
    from ctypes import windll, wintypes

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ModuleNotFoundError:
    exit("fuse module not found, please install fusepy to mount images "
         "(`{} -mpip install https://github.com/billziss-gh/fusepy/archive/windows.zip`).".format(_common.python_cmd))
except Exception as e:
    exit("Failed to import the fuse module:\n"
         "{}: {}".format(type(e).__name__, e))

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ModuleNotFoundError:
    exit("Cryptodome module not found, please install pycryptodomex for encryption support "
             "(`{} install pycryptodomex`).".format(_common.python_cmd))
except Exception as e:
    exit("Failed to import the Cryptodome module:\n"
         "{}: {}".format(type(e).__name__, e))


class SDFilesystemMount(LoggingMixIn, Operations):
    def path_to_iv(self, path):
        path_hash = sha256(path[self.root_len + 33:].lower().encode('utf-16le') + b'\0\0').digest()
        hash_p1 = util.readbe(path_hash[0:16])
        hash_p2 = util.readbe(path_hash[16:32])
        return hash_p1 ^ hash_p2

    def __init__(self, sd_dir: str, movable: str, dev: bool = False, readonly: bool = False):
        self.fds = {}
        self.crypto = crypto.CTRCrypto(is_dev=dev)

        self.crypto.setup_keys_from_boot9()

        mv = open(movable, 'rb')
        mv.seek(0x110)
        key_y = mv.read(0x10)
        mv.close()
        key_hash = sha256(key_y).digest()
        hash_parts = unpack('<IIII', key_hash[0:16])
        self.root_dir = '{0[0]:08x}{0[1]:08x}{0[2]:08x}{0[3]:08x}'.format(hash_parts)

        if not os.path.isdir(sd_dir + '/' + self.root_dir):
            exit('Failed to find {} in the SD dir.'.format(self.root_dir))

        print('Root dir: ' + self.root_dir)

        self.crypto.set_keyslot('y', 0x34, util.readbe(key_y))
        print('Key:      ' + self.crypto.key_normal[0x34].hex())

        self.root = os.path.realpath(sd_dir + '/' + self.root_dir)
        self.root_len = len(self.root)

        self.readonly = readonly

    # noinspection PyMethodOverriding
    def __call__(self, op, path, *args):
        return super().__call__(op, self.root + path, *args)

    def destroy(self, path):
        for f in self.fds.values():
            f.close()

    def access(self, path, mode):
        if not os.access(path, mode):
            raise FuseOSError(EACCES)

    chmod = os.chmod

    def chown(self, path, *args, **kwargs):
        if not _common.windows:
            os.chown(path, *args, **kwargs)

    def create(self, path, mode, **kwargs):
        if self.readonly:
            raise FuseOSError(EROFS)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        self.fds[fd] = os.fdopen(fd, 'wb')
        return fd

    def flush(self, path, fh):
        try:
            os.fsync(fh)
        except OSError as e:
            # I am not sure why this is happening on Windows. if anyone can give me a hint, please do.
            if e.errno != EBADF:  # "Bad file descriptor"
                raise
        return

    def fsync(self, path, datasync, fh):
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
            raise FuseOSError(EROFS)
        if not _common.windows:
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
        yield from ('.', '..')
        ld = os.listdir(path)
        if _common.windows:
            # I should figure out how to mark hidden files, if possible
            yield from (d for d in ld if not d.startswith('.'))
        else:
            yield from ld

    readlink = os.readlink

    def release(self, path, fh):
        self.fds[fh].close()
        del self.fds[fh]

    def rename(self, old, new):
        # renaming's too difficult. just copy the file to the name you want if you really need it.
        raise FuseOSError(EROFS if self.readonly else EPERM)

    rmdir = os.rmdir

    def statfs(self, path):
        if _common.windows:
            lpSectorsPerCluster = c_ulonglong(0)
            lpBytesPerSector = c_ulonglong(0)
            lpNumberOfFreeClusters = c_ulonglong(0)
            lpTotalNumberOfClusters = c_ulonglong(0)
            ret = windll.kernel32.GetDiskFreeSpaceW(c_wchar_p(path), pointer(lpSectorsPerCluster),
                                                    pointer(lpBytesPerSector),
                                                    pointer(lpNumberOfFreeClusters),
                                                    pointer(lpTotalNumberOfClusters))
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
            raise FuseOSError(EROFS)
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


def main():
    parser = ArgumentParser(description='Mount Nintendo 3DS SD card contents.',
                            parents=(_common.default_argp, _common.readonly_argp, _common.dev_argp,
                                              _common.main_positional_args(
                                                  'sd_dir', "path to folder with SD contents (on SD: /Nintendo 3DS)")))
    parser.add_argument('--movable', metavar='MOVABLESED', help='path to movable.sed', required=True)

    a = parser.parse_args()
    opts = dict(_common.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    mount = SDFilesystemMount(sd_dir=a.sd_dir, movable=a.movable, dev=a.dev, readonly=a.ro)
    if _common.macos or _common.windows:
        opts['fstypename'] = 'SDCARD'
        if _common.macos:
            opts['volname'] = "Nintendo 3DS SD Card ({})".format(mount.root_dir)
        else:
            # windows
            opts['volname'] = "Nintendo 3DS SD Card ({}…)".format(mount.root_dir[0:8])
            opts['case_insensitive'] = False
    fuse = FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=a.ro, nothreads=True, debug=a.d,
                fsname=os.path.realpath(a.sd_dir).replace(',', '_'), **opts)


if __name__ == '__main__':
    print('Note: You should be calling this script as "mount_{0}" or "{1} -mfuse3ds {0}" '
          'instead of calling it directly.'.format('sd', _common.python_cmd))
    main()
