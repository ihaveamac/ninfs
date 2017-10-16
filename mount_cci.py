#!/usr/bin/env python3

import argparse
import errno
import hashlib
import logging
import os
import stat
import struct
import sys

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ImportError:
    sys.exit('fuse module not found, please install fusepy to mount images (`pip3 install git+https://github.com/billziss-gh/fusepy.git`).')


# since this is used often enough
def readle(b):
    return int.from_bytes(b, 'little')


class CTRCartImage(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, cci):
        # get status change, modify, and file access times
        cci_stat = os.stat(cci)
        self.g_stat = {}
        self.g_stat['st_ctime'] = int(cci_stat.st_ctime)
        self.g_stat['st_mtime'] = int(cci_stat.st_mtime)
        self.g_stat['st_atime'] = int(cci_stat.st_atime)

        # open cci and get section sizes
        self.f = open(cci, 'rb')
        self.f.seek(0x100)
        ncsd_header = self.f.read(0x100)
        if ncsd_header[0:4] != b'NCSD':
            sys.exit('NCSD magic not found, is this a real CCI?')
        media_id = ncsd_header[0x8:0x10]
        if media_id == b'\0' * 8:
            sys.exit('Media ID is all-zero, is this a CCI?')

        self.cci_size = readle(ncsd_header[4:8]) * 0x200

        # create initial virtual files
        self.files = {}
        self.files['/ncsd.bin'] = {'size': 0x200, 'offset': 0}
        self.files['/cardinfo.bin'] = {'size': 0x1000, 'offset': 0x200}
        self.files['/devinfo.bin'] = {'size': 0x300, 'offset': 0x1200}

        ncsd_part_raw = ncsd_header[0x20:0x60]
        ncsd_partitions = [[readle(ncsd_part_raw[i:i + 4]) * 0x200,
                            readle(ncsd_part_raw[i + 4:i + 8]) * 0x200] for i in range(0, 0x40, 0x8)]

        ncsd_part_names = ['game', 'manual', 'dlp', 'unk', 'unk', 'unk', 'update_n3ds', 'update_o3ds']
        for idx, part in enumerate(ncsd_partitions):
            if part[0]:
                self.files['/content{}.{}.ncch'.format(idx, ncsd_part_names[idx])] = {'size': part[1], 'offset': part[0]}

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
        self.f.seek(real_offset)
        return self.f.read(size)

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
        return {'f_bsize': 4096, 'f_blocks': self.cci_size // 4096, 'f_bavail': 0, 'f_bfree': 0, 'f_files': len(self.files)}

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
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS CTR Cart Image files.')
    parser.add_argument('--fg', '-f', help='run in foreground', action='store_true')
    parser.add_argument('--do', help='debug output (python logging module)', action='store_true')
    parser.add_argument('-o', metavar='OPTIONS', help='mount options')
    parser.add_argument('cci', help='CCI file')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()
    try:
        opts = {o: True for o in a.o.split(',')}
    except AttributeError:
        opts = {}

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    fuse = FUSE(CTRCartImage(cci=a.cci), a.mount_point, foreground=a.fg or a.do, fsname=os.path.realpath(a.cci), ro=True, **opts)
