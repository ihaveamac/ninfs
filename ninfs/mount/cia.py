# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts CTR Importable Archive (CIA) files, creating a virtual filesystem of decrypted contents (if encrypted) + Ticket,
Title Metadata, and Meta region (if exists).

DLC with missing contents is currently not supported.
"""

import logging
import os
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from struct import unpack
from sys import argv
from typing import BinaryIO, Dict

from pyctr.crypto import CryptoEngine, Keyslot
from pyctr.types.tmd import TitleMetadataReader, CHUNK_RECORD_SIZE
from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
from .ncch import NCCHContainerMount
from .srl import SRLMount


# based on http://stackoverflow.com/questions/1766535/bit-hack-round-off-to-multiple-of-8/1766566#1766566
def new_offset(x: int) -> int:
    return ((x + 63) >> 6) << 6  # - x


class CTRImportableArchiveMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, cia_fp: BinaryIO, g_stat: os.stat_result, dev: bool = False, seeddb: bool = None):
        self.crypto = CryptoEngine(dev=dev)

        self.dev = dev
        self.seeddb = seeddb

        self._g_stat = g_stat
        # get status change, modify, and file access times
        self.g_stat = {'st_ctime': int(g_stat.st_ctime), 'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        # open cia and get section sizes
        archive_header_size, cia_type, cia_version, cert_chain_size, \
            ticket_size, tmd_size, meta_size, content_size = unpack('<IHHIIIIQ', cia_fp.read(0x20))

        self.cia_size = new_offset(archive_header_size) + new_offset(cert_chain_size) + new_offset(ticket_size)\
            + new_offset(tmd_size) + new_offset(meta_size) + new_offset(content_size)

        # get offsets for sections of the CIA
        # each section is aligned to 64-byte blocks
        cert_chain_offset = new_offset(archive_header_size)
        ticket_offset = cert_chain_offset + new_offset(cert_chain_size)
        tmd_offset = ticket_offset + new_offset(ticket_size)
        self.content_offset = tmd_offset + new_offset(tmd_size)
        meta_offset = self.content_offset + new_offset(content_size)

        # load tmd
        cia_fp.seek(tmd_offset)
        self.tmd = TitleMetadataReader.load(cia_fp)
        self.title_id = self.tmd.title_id

        # load titlekey
        cia_fp.seek(ticket_offset)
        self.crypto.load_from_ticket(cia_fp.read(ticket_size))

        # create virtual files
        self.files = {'/header.bin': {'size': archive_header_size, 'offset': 0, 'type': 'raw'},
                      '/cert.bin': {'size': cert_chain_size, 'offset': cert_chain_offset, 'type': 'raw'},
                      '/ticket.bin': {'size': ticket_size, 'offset': ticket_offset, 'type': 'raw'},
                      '/tmd.bin': {'size': tmd_size, 'offset': tmd_offset, 'type': 'raw'},
                      '/tmdchunks.bin': {'size': self.tmd.content_count * CHUNK_RECORD_SIZE,
                                         'offset': tmd_offset + 0xB04, 'type': 'raw'}}
        if meta_size:
            self.files['/meta.bin'] = {'size': meta_size, 'offset': meta_offset, 'type': 'raw'}
            # show icon.bin if meta size is the expected size
            # in practice this never changes, but better to be safe
            if meta_size == 0x3AC0:
                self.files['/icon.bin'] = {'size': 0x36C0, 'offset': meta_offset + 0x400, 'type': 'raw'}

        self.dirs: Dict[str, NCCHContainerMount] = {}

        self.f = cia_fp

    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass

    destroy = __del__

    def init(self, path):
        # read chunks to generate virtual files
        current_offset = self.content_offset
        for chunk in self.tmd.chunk_records:
            is_srl = chunk.cindex == 0 and self.title_id[3:5] == '48'
            file_ext = 'nds' if is_srl else 'ncch'
            filename = f'/{chunk.cindex:04x}.{chunk.id}.{file_ext}'
            self.files[filename] = {'size': chunk.size, 'offset': current_offset,
                                    'index': chunk.cindex.to_bytes(2, 'big'),
                                    'type': 'enc' if chunk.type.encrypted else 'raw'}
            current_offset += new_offset(chunk.size)

            dirname = f'/{chunk.cindex:04x}.{chunk.id}'
            # noinspection PyBroadException
            try:
                content_vfp = _c.VirtualFileWrapper(self, filename, chunk.size)
                if is_srl:
                    content_fuse = SRLMount(content_vfp, g_stat=self._g_stat)
                else:
                    content_fuse = NCCHContainerMount(content_vfp, dev=self.dev, g_stat=self._g_stat, seeddb=self.seeddb)
                content_fuse.init(path)
                self.dirs[dirname] = content_fuse
            except Exception as e:
                print(f'Failed to mount {filename}: {type(e).__name__}: {e}')

    def flush(self, path, fh):
        return self.f.flush()

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].getattr(_c.remove_first_dir(path), fh)
        uid, gid, pid = fuse_get_context()
        if path == '/' or path in self.dirs:
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        elif path in self.files:
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': self.files[path]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    @_c.ensure_lower_path
    def readdir(self, path, fh):
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            yield from self.dirs[first_dir].readdir(_c.remove_first_dir(path), fh)
        else:
            yield from ('.', '..')
            yield from (x[1:] for x in self.files)
            yield from (x[1:] for x in self.dirs)

    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].read(_c.remove_first_dir(path), size, offset, fh)
        fi = self.files[path]
        real_offset = fi['offset'] + offset
        if fi['offset'] + offset > fi['offset'] + fi['size']:
            return b''
        if offset + size > fi['size']:
            size = fi['size'] - offset
        real_size = size

        if fi['type'] == 'raw':
            # if raw, just read and return
            self.f.seek(real_offset)
            data = self.f.read(size)

        elif fi['type'] == 'enc':
            # if encrypted, the block needs to be decrypted first
            # CBC requires a full block (0x10 in this case). and the previous
            #   block is used as the IV. so that's quite a bit to read if the
            #   application requires just a few bytes.
            # thanks Stary2001
            before = offset % 16
            if size % 16 != 0:
                size = size + 16 - size % 16
            if offset - before == 0:
                # use the initial value if reading from the first block
                # noinspection PyTypeChecker
                iv = fi['index'] + (b'\0' * 14)
            else:
                # use the previous block if reading anywhere else
                self.f.seek(real_offset - before - 0x10)
                iv = self.f.read(0x10)
            # read to block size
            self.f.seek(real_offset - before)
            # adding 0x10 to the size fixes some kind of decryption bug
            data = self.crypto.create_cbc_cipher(Keyslot.DecryptedTitlekey,
                                                 iv).decrypt(self.f.read(size + 0x10))[before:real_size + before]

        else:
            from pprint import pformat
            print('--------------------------------------------------',
                  'Warning: unknown file type (this should not happen!)',
                  'Please file an issue or contact the developer with the details below.',
                  '  https://github.com/ihaveamac/ninfs/issues',
                  '--------------------------------------------------',
                  f'{path!r}: {pformat(fi)!r}', sep='\n')

            data = b'g' * size

        return data

    @_c.ensure_lower_path
    def statfs(self, path):
        first_dir = _c.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].statfs(_c.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.cia_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description="Mount Nintendo 3DS CTR Importable Archive files.",
                            parents=(_c.default_argp, _c.dev_argp, _c.seeddb_argp,
                                     _c.main_args('cia', "CIA file")))

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    cia_stat = os.stat(a.cia)

    with open(a.cia, 'rb') as f:
        mount = CTRImportableArchiveMount(cia_fp=f, dev=a.dev, g_stat=cia_stat, seeddb=a.seeddb)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'CIA'
            if _c.macos:
                opts['volname'] = f'CTR Importable Archive ({mount.title_id.upper()})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = f'CIA ({mount.title_id.upper()})'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=os.path.realpath(a.cia).replace(',', '_'), **opts)
