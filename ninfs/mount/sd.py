# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts SD contents under `/Nintendo 3DS`, creating a virtual filesystem with decrypted contents. movable.sed required.
"""

import logging
import os
from errno import EPERM, EACCES
from hashlib import sha256
from sys import exit, argv

from pyctr.crypto import CryptoEngine, Keyslot
from pyctr.util import readbe
from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context

if _c.windows:
    from ctypes import c_wchar_p, pointer, c_ulonglong, windll, wintypes


class SDFilesystemMount(LoggingMixIn, Operations):
    fd = 0

    @_c.ensure_lower_path
    def path_to_iv(self, path):
        return CryptoEngine.sd_path_to_iv(path[self.root_len + 33:])

    def __init__(self, sd_dir: str, movable: bytes, dev: bool = False, readonly: bool = False, boot9: str = None):
        self.crypto = CryptoEngine(boot9=boot9, dev=dev)

        self.crypto.setup_sd_key(movable)
        self.root_dir = self.crypto.id0.hex()

        if not os.path.isdir(sd_dir + '/' + self.root_dir):
            exit(f'Failed to find {self.root_dir} in the SD dir.')

        print('Root dir: ' + self.root_dir)
        print('Key:      ' + self.crypto.keygen(Keyslot.SD).hex())

        self.root = os.path.realpath(sd_dir + '/' + self.root_dir)
        self.root_len = len(self.root)

        self.readonly = readonly

    # noinspection PyMethodOverriding
    def __call__(self, op, path, *args):
        return super().__call__(op, self.root + path, *args)

    def access(self, path, mode):
        if not os.access(path, mode):
            raise FuseOSError(EACCES)

    @_c.raise_on_readonly
    def chmod(self, path, mode):
        os.chmod(path, mode)

    @_c.raise_on_readonly
    def chown(self, path, *args, **kwargs):
        if not _c.windows:
            os.chown(path, *args, **kwargs)

    @_c.raise_on_readonly
    def create(self, path, mode, **kwargs):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        os.close(fd)
        self.fd += 1
        return self.fd

    def getattr(self, path, fh=None):
        st = os.lstat(path)
        uid, gid, _ = fuse_get_context()
        res = {key: getattr(st, key) for key in ('st_atime', 'st_ctime', 'st_mode', 'st_mtime', 'st_nlink', 'st_size',
                                                 'st_flags') if hasattr(st, key)}
        res['st_uid'] = st.st_uid if st.st_uid != 0 else uid
        res['st_gid'] = st.st_gid if st.st_gid != 0 else gid
        return res

    getxattr = None

    def link(self, target, source):
        return os.link(source, target)

    listxattr = None

    @_c.raise_on_readonly
    def mkdir(self, path, *args, **kwargs):
        os.mkdir(path, *args, **kwargs)

    @_c.raise_on_readonly
    def mknod(self, path, *args, **kwargs):
        if not _c.windows:
            os.mknod(path, *args, **kwargs)

    # open = os.open
    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def read(self, path, size, offset, fh):
        # special check for special files
        if os.path.basename(path).startswith('.') or 'nintendo dsiware' in path:
            with open(path, 'rb') as f:
                f.seek(offset)
                return f.read(size)

        before = offset % 16
        with open(path, 'rb') as f:
            f.seek(offset - before)
            data = f.read(size + before)
        iv = self.path_to_iv(path) + (offset >> 4)
        return self.crypto.create_ctr_cipher(Keyslot.SD, iv).decrypt(data)[before:]

    def readdir(self, path, fh):
        yield from ('.', '..')
        ld = os.listdir(path)
        if _c.windows:
            # I should figure out how to mark hidden files, if possible
            yield from (d for d in ld if not d.startswith('.'))
        else:
            yield from ld

    readlink = os.readlink

    @_c.raise_on_readonly
    def rename(self, old, new):
        # renaming's too difficult. just copy the file to the name you want if you really need it.
        raise FuseOSError(EPERM)

    @_c.raise_on_readonly
    def rmdir(self, path):
        os.rmdir(path)

    # noinspection PyPep8Naming
    def statfs(self, path):
        if _c.windows:
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
            return {key: getattr(stv, key) for key in ('f_bavail', 'f_bfree', 'f_blocks', 'f_bsize', 'f_favail',
                                                       'f_ffree', 'f_files', 'f_frsize', 'f_namemax')}

    def symlink(self, target, source):
        return os.symlink(source, target)

    def truncate(self, path, length, fh=None):
        with open(path, 'r+b') as f:
            f.truncate(length)

    @_c.raise_on_readonly
    def unlink(self, path, *args, **kwargs):
        os.unlink(path)

    @_c.raise_on_readonly
    def utimens(self, path, *args, **kwargs):
        os.utime(path, *args, **kwargs)

    @_c.raise_on_readonly
    def write(self, path, data, offset, fh):
        # special check for special files
        if os.path.basename(path).startswith('.') or 'nintendo dsiware' in path.lower():
            with open(path, 'rb+') as f:
                f.seek(offset)
                return f.write(data)

        before = offset % 16
        iv = self.path_to_iv(path) + (offset >> 4)
        out_data = self.crypto.create_ctr_cipher(Keyslot.SD, iv).decrypt((b'\0' * before) + data)[before:]

        with open(path, 'rb+') as f:
            f.seek(offset)
            return f.write(out_data)


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS SD card contents.',
                            parents=(_c.default_argp, _c.readonly_argp, _c.ctrcrypto_argp,
                                     _c.main_args(
                                         'sd_dir', "path to folder with SD contents (on SD: /Nintendo 3DS)")))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--movable', metavar='MOVABLESED', help='path to movable.sed')
    group.add_argument('--sd-key', metavar='SDKEY', help='SD key as hexstring')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    if a.movable:
        with open(a.movable, 'rb') as f:
            movable = f.read(0x140)
    else:
        movable = bytes.fromhex(a.sd_key)

    mount = SDFilesystemMount(sd_dir=a.sd_dir, movable=movable, dev=a.dev, readonly=a.ro, boot9=a.boot9)
    if _c.macos or _c.windows:
        opts['fstypename'] = 'SDCard'
        if _c.macos:
            opts['volname'] = f'Nintendo 3DS SD Card ({mount.root_dir})'
            opts['noappledouble'] = True  # fixes an error. but this is probably not the best way to do it.
        else:
            # windows
            opts['volname'] = f'Nintendo 3DS SD Card ({mount.root_dir[0:8]}…)'
            opts['case_insensitive'] = False
    FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=a.ro, nothreads=True, debug=a.d,
         fsname=os.path.realpath(a.sd_dir).replace(',', '_'), **opts)
