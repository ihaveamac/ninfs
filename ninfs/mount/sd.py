# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts SD contents under `/Nintendo 3DS`, creating a virtual filesystem with decrypted contents. movable.sed required.
"""

import logging
import os
from errno import EPERM, EACCES
from sys import exit, argv
from threading import Lock
from typing import TYPE_CHECKING

from pyctr.crypto import CryptoEngine, Keyslot

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, realpath

if _c.windows:
    from ctypes import c_wchar_p, pointer, c_ulonglong, windll, wintypes

if TYPE_CHECKING:
    from typing import BinaryIO, Dict, Optional, Tuple


class SDFilesystemMount(LoggingMixIn, Operations):

    @_c.ensure_lower_path
    def path_to_iv(self, path):
        return CryptoEngine.sd_path_to_iv(path[self.root_len + 33:])

    def fd_to_fileobj(self, path, mode, fd):
        fh = open(fd, mode, buffering=0)
        lock = Lock()
        if not (os.path.basename(path).startswith('.') or 'nintendo dsiware' in path.lower()):
            fh_enc = self.crypto.create_ctr_io(Keyslot.SD, fh, self.path_to_iv(path))
            fh_group = (fh_enc, fh, lock)
        else:
            fh_group = (fh, None, lock)
        self.fds[fd] = fh_group
        return fd

    def __init__(self, sd_dir: str, movable: bytes, dev: bool = False, readonly: bool = False, boot9: str = None):
        self.crypto = CryptoEngine(boot9=boot9, dev=dev)

        # only allows one create/open/release operation at a time
        self.global_lock = Lock()

        # each fd contains a tuple with a file object, a base file object (for encrypted files),
        #   and a thread lock to prevent two read or write operations from screwing with eachother
        self.fds: 'Dict[int, Tuple[BinaryIO, Optional[BinaryIO], Lock]]' = {}

        self.crypto.setup_sd_key(movable)
        self.root_dir = self.crypto.id0.hex()

        if not os.path.isdir(sd_dir + '/' + self.root_dir):
            exit(f'Could not find ID0 {self.root_dir} in the SD directory.')

        print('ID0:', self.root_dir)
        print('Key:', self.crypto.keygen(Keyslot.SD).hex())

        self.root = realpath(sd_dir + '/' + self.root_dir)
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
    def create(self, path, mode, fi=None):
        # prevent another create/open/release from interfering
        with self.global_lock:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
            return self.fd_to_fileobj(path, 'wb+', fd)

    @_c.raise_on_readonly
    def flush(self, path, fh):
        fd, _, lock = self.fds[fh]
        with lock:
            fd.flush()

    def getattr(self, path, fh=None):
        st = os.lstat(path)
        uid, gid, _ = fuse_get_context()
        res = {key: getattr(st, key) for key in ('st_atime', 'st_ctime', 'st_mode', 'st_mtime', 'st_nlink', 'st_size',
                                                 'st_flags') if hasattr(st, key)}
        res['st_uid'] = st.st_uid if st.st_uid != 0 else uid
        res['st_gid'] = st.st_gid if st.st_gid != 0 else gid
        return res

    def link(self, target, source):
        return os.link(source, target)

    @_c.raise_on_readonly
    def mkdir(self, path, mode):
        os.mkdir(path, mode)

    @_c.raise_on_readonly
    def mknod(self, path, mode, dev):
        if not _c.windows:
            os.mknod(path, mode, dev)

    # open = os.open
    def open(self, path, flags):
        # prevent another create/open/release from interfering
        with self.global_lock:
            fd = os.open(path, flags)
            return self.fd_to_fileobj(path, 'rb+', fd)

    def read(self, path, size, offset, fh):
        fd, _, lock = self.fds[fh]

        # acquire lock to prevent another read/write from messing with this operation
        with lock:
            fd.seek(offset)
            return fd.read(size)

    def readdir(self, path, fh):
        yield from ('.', '..')

        # due to DSiWare exports having unique crypto that is a pain to handle, this hides it to prevent misleading
        #   users into thinking that the files are decrypted.
        ld = (d for d in os.listdir(path) if not d.lower() == 'nintendo dsiware')

        if _c.windows:
            # I should figure out how to mark hidden files, if possible
            yield from (d for d in ld if not d.startswith('.'))
        else:
            yield from ld

    readlink = os.readlink

    def release(self, path, fh):
        # prevent another create/open/release from interfering
        with self.global_lock:
            fd_group = self.fds[fh]
            # prevent use of the handle while cleaning up, or closing while in use
            with fd_group[2]:
                fd_group[0].close()
                try:
                    fd_group[1].close()
                except AttributeError:
                    # unencrypted files have the second item set to None
                    pass
                del self.fds[fh]

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
        try:
            fd, _, lock = self.fds[fh]
            # acquire lock to prevent another read/write from messing with this operation
            with lock:
                fd.truncate(length)

        except KeyError:  # in case this is not an already open file
            with open(path, 'rb+') as f:
                f.truncate(length)

    @_c.raise_on_readonly
    def unlink(self, path):
        os.unlink(path)

    @_c.raise_on_readonly
    def utimens(self, path, *args, **kwargs):
        os.utime(path, *args, **kwargs)

    @_c.raise_on_readonly
    def write(self, path, data, offset, fh):
        fd, _, lock = self.fds[fh]

        # acquire lock to prevent another read/write from messing with this operation
        with lock:
            fd.seek(offset)
            return fd.write(data)


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
            # this fixes an issue with creating files through Finder
            # a better fix would probably be to support xattrs properly, but given the kind of data and filesystem
            #   that this code would interact with, it's not really useful.
            opts['noappledouble'] = True
        else:
            # windows
            opts['volname'] = f'Nintendo 3DS SD Card ({mount.root_dir[0:8]}…)'
            opts['case_insensitive'] = False
    FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=a.ro, debug=a.d,
         fsname=realpath(a.sd_dir).replace(',', '_'), **opts)
