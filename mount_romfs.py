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


# since this is used often enough
def readle(b):
    return int.from_bytes(b, 'little')


def roundup(offset, alignment):
    return math.ceil(offset / alignment) * alignment


class RomFS(LoggingMixIn, Operations):
    fd = 0

    def _get_item(self, path):
        curr = self.root
        if path[0] == '/':
            path = path[1:]
        for part in path.split('/'):
            if part == '':
                return curr
            try:
                curr = curr['contents'][part]
            except KeyError:
                raise FuseOSError(errno.ENOENT)
        return curr

    def __init__(self, romfs):
        # get status change, modify, and file access times
        romfs_stat = os.stat(romfs)
        self.g_stat = {}
        self.g_stat['st_ctime'] = int(romfs_stat.st_ctime)
        self.g_stat['st_mtime'] = int(romfs_stat.st_mtime)
        self.g_stat['st_atime'] = int(romfs_stat.st_atime)

        self.romfs_size = os.path.getsize(romfs)

        # open file, read IVFC header and verify
        self.f = open(romfs, 'rb')
        ivfc_header = self.f.read(0x60)
        if ivfc_header[0:4] != b'IVFC':
            # TODO: maybe handle lv3 that starts at offset 0. this may happen
            #   since a 3DSX romfs does not have the IVFC header. also, HANS
            #   once required it be removed to be used as a replacement.
            sys.exit('IVFC magic not found, is this a RomFS?')

        # get the offset of lv3 which is where the contents are
        master_hash_size = readle(ivfc_header[0x8:0xC])
        lv3_blocksize = readle(ivfc_header[0x4C:0x50])
        lv3_hashblocksize = 1 << lv3_blocksize
        self.body_offset = roundup(0x60 + master_hash_size, lv3_hashblocksize)

        # read RomFS lv3 header
        # only lv3 is necessary when reading files. the others are just for
        #   hash verification I think.
        # TODO: verify using https://github.com/d0k3/GodMode9/blob/26acfc4cff1e6314af62013e0e019210e7bc2c8d/source/game/romfs.c#L4-L12
        self.f.seek(self.body_offset)
        romfs_header = self.f.read(0x28)
        dirmeta_offset = readle(romfs_header[0xC:0x10])
        dirmeta_size = readle(romfs_header[0x10:0x14])
        filemeta_offset = readle(romfs_header[0x1C:0x20])
        filemeta_size = readle(romfs_header[0x20:0x24])
        filedata_offset = readle(romfs_header[0x24:0x28])

        def iterate_dir(out, raw_metadata):
            next_sibling_dir = readle(raw_metadata[0x4:0x8])
            first_child_dir = readle(raw_metadata[0x8:0xC])
            first_file = readle(raw_metadata[0xC:0x10])
            next_dir = readle(raw_metadata[0x10:0x14])

            out['type'] = 'dir'
            out['contents'] = {}

            # iterate through all child dirs
            if first_child_dir != 0xFFFFFFFF:
                self.f.seek(self.body_offset + dirmeta_offset + first_child_dir)
                while True:
                    child_dir_meta = self.f.read(0x18)
                    next_sibling_dir = readle(child_dir_meta[0x4:0x8])
                    child_dir_filename = self.f.read(readle(child_dir_meta[0x14:0x18])).decode('utf-16le')
                    out['contents'][child_dir_filename] = {}

                    iterate_dir(out['contents'][child_dir_filename], child_dir_meta)
                    if next_sibling_dir == 0xFFFFFFFF:
                        break
                    self.f.seek(self.body_offset + dirmeta_offset + next_sibling_dir)

            # iterate through all files
            if first_file != 0xFFFFFFFF:
                self.f.seek(self.body_offset + filemeta_offset + first_file)
                while True:
                    child_file_meta = self.f.read(0x20)
                    next_sibling_file = readle(child_file_meta[0x4:0x8])
                    child_file_offset = readle(child_file_meta[0x8:0x10])
                    child_file_size = readle(child_file_meta[0x10:0x18])
                    child_file_filename = self.f.read(readle(child_file_meta[0x1C:0x20])).decode('utf-16le')
                    out['contents'][child_file_filename] = {'type': 'file', 'offset': self.body_offset + filedata_offset + child_file_offset, 'size': child_file_size}
                    if next_sibling_file == 0xFFFFFFFF:
                        break
                    self.f.seek(self.body_offset + filemeta_offset + next_sibling_file)

        # create root dictionary
        self.root = {}
        self.f.seek(self.body_offset + dirmeta_offset)
        root_meta = self.f.read(0x18)
        iterate_dir(self.root, root_meta)

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
        item = self._get_item(path)
        if item['type'] == 'dir':
            st = {'st_mode': (stat.S_IFDIR | 0o555), 'st_nlink': 2}
        elif item['type'] == 'file':
            st = {'st_mode': (stat.S_IFREG | 0o444), 'st_size': item['size'], 'st_nlink': 1}
        else:
            # this won't happen unless I fucked up
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
        item = self._get_item(path)
        return ['.', '..', *item['contents'].keys()]

    def read(self, path, size, offset, fh):
        item = self._get_item(path)
        self.f.seek(item['offset'] + offset)
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
        item = self._get_item(path)
        return {'f_bsize': 4096, 'f_blocks': self.romfs_size // 4096, 'f_bavail': 0, 'f_bfree': 0, 'f_files': len(item['contents'])}

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
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS Read-only Filesystem (RomFS) files.')
    parser.add_argument('--fg', '-f', help='run in foreground', action='store_true')
    parser.add_argument('--do', help='debug output (python logging module)', action='store_true')
    parser.add_argument('-o', metavar='OPTIONS', help='mount options')
    parser.add_argument('romfs', help='RomFS file')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()
    try:
        opts = {o: True for o in a.o.split(',')}
    except AttributeError:
        opts = {}

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    fuse = FUSE(RomFS(romfs=a.romfs), a.mount_point, foreground=a.fg or a.do, fsname=os.path.realpath(a.romfs), ro=True, **opts)
