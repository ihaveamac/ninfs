# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts iQue Player NAND images, creating a virtual filesystem of the files contained within.
"""

import logging
from errno import ENOENT, EROFS
from stat import S_IFDIR, S_IFREG
from sys import exit, argv
from typing import BinaryIO

from pyctr.util import readbe

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, realpath

class BBNandImageMount(LoggingMixIn, Operations):
    fd = 0
    
    def __init__(self, nand_fp: BinaryIO, g_stat: dict):
        self.g_stat = g_stat
        
        self.files = {}
        
        self.f = nand_fp
        
    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass
    
    destroy = __del__
    
    def init(self, path):
        nand_size = self.f.seek(0, 2)
        if nand_size != 0x4000000:
            exit(f'NAND size is incorrect (expected 0x4000000, got {nand_size:#X})')
        
        bbfs_blocks = []
        self.f.seek(0xFF0 * 0x4000)
        for i in range(0x10):
            bbfs_blocks.append(self.f.read(0x4000))
        
        self.f.seek(0)
        
        latest_seqno = -1
        latest_bbfs_block = None
        
        for i, j in enumerate(bbfs_blocks):
            header = j[0x3FF4:]
            
            magic = header[:4]
            if magic == b"\0x00\0x00\0x00\0x00":
                continue
            if magic not in [b"BBFS", b"BBFL"]:
                exit(f'Invalid BBFS magic: expected b"BBFS" or b"BBFL", got {magic.hex().upper()}')
            
            calculated_checksum = 0
            for k in range(0, 0x4000, 2):
                calculated_checksum += readbe(j[k:k + 2])
            
            if calculated_checksum & 0xFFFF != 0xCAD7:
                exit(f'BBFS block {i} has an invalid checksum')
            
            seqno = readbe(header[4:8])
            if seqno > latest_seqno:
                latest_seqno = seqno
                latest_bbfs_block = i
        
        if latest_bbfs_block == None or latest_seqno == -1:
            exit(f'Blank BBFS (all BBFS magics were 00000000)')
        
        self.used = 0
        
        for i in range(0x2000, 0x3FF4, 0x14):
            entry = bbfs_blocks[latest_bbfs_block][i:i + 0x14]
            valid = bool(entry[11])
            u = readbe(entry[12:14])
            start = u - (u & 0x8000) * 2
            if valid and start != -1:
                name = entry[:8].decode().rstrip("\x00")
                ext = entry[8:11].decode().rstrip("\x00")
                size = readbe(entry[16:20])
                self.files[f'/{name}.{ext}'] = {'start': start, 'size': size}
                self.used += size // 0x4000
        
        fat = bbfs_blocks[latest_bbfs_block][:0x2000]
        
        self.fat_entries = []
        for i in range(0, len(fat), 2):
            u = readbe(fat[i:i + 2])
            s = u - (u & 0x8000) * 2
            self.fat_entries.append(s)
    
    def flush(self, path, fh):
        return self.f.flush()
    
    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        if path == '/':
            st = {'st_mode': (S_IFDIR | 0o777), 'st_nlink': 2}
        elif path in self.files:
            st = {'st_mode': (S_IFREG | 0o666),
                  'st_size': self.files[path]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}
    
    def open(self, path, flags):
        self.fd += 1
        return self.fd
    
    @_c.ensure_lower_path
    def readdir(self, path, fh):
        yield from ('.', '..')
        yield from (x[1:] for x in self.files)
    
    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        fi = self.files[path]
        
        if offset > fi['size']:
            return b''
        
        data = bytearray()
        
        block = fi['start']
        while True:
            self.f.seek(block * 0x4000)
            data.extend(self.f.read(0x4000))
            block = self.fat_entries[block]
            if block == -1:
                break
            if block in [0, -2, -3]:
                return b''
        
        if len(data) != fi['size']:
            return b''
        
        if offset + size > fi['size']:
            size = fi['size'] - offset
        
        return bytes(data[offset:offset + size])
    
    @_c.ensure_lower_path
    def statfs(self, path):
        return {'f_bsize': 0x4000, 'f_frsize': 0x4000, 'f_blocks': 0xFF0 - 0x40, 'f_bavail': 0xFF0 - 0x40 - self.used,
                'f_bfree': 0xFF0 - 0x40 - self.used, 'f_files': len(self.files)}
    
    @_c.ensure_lower_path
    def write(self, path, data, offset, fh):
        raise FuseOSError(EROFS)


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount iQue Player NAND images.',
                            parents=(_c.default_argp, _c.main_args('nand', 'iQue Player NAND image')))
    
    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))
    
    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)
    
    nand_stat = get_time(a.nand)
    
    with open(a.nand, 'rb') as f:
        mount = BBNandImageMount(nand_fp=f, g_stat=nand_stat)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'BBFS'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            if _c.macos:
                path_to_show = realpath(a.nand).rsplit('/', maxsplit=2)
                opts['volname'] = f'iQue Player NAND ({path_to_show[-2]}/{path_to_show[-1]})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = 'iQue Player NAND'
        FUSE(mount, a.mount_point, foreground=a.fg or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=realpath(a.nand).replace(',', '_'), **opts)
