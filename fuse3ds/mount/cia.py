#!/usr/bin/env python3

"""
Mounts CTR Importable Archive (CIA) files, creating a virtual filesystem of decrypted contents (if encrypted) + Ticket, Title Metadata, and Meta region (if exists).

DLC with missing contents is currently not supported.
"""

import logging
import os
from argparse import ArgumentParser
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from struct import unpack
from sys import exit
from typing import BinaryIO

from pyctr.crypto import CTRCrypto
from pyctr.tmd import TitleMetadataReader, CHUNK_RECORD_SIZE
from pyctr.util import readbe

from . import _common
from .ncch import NCCHContainerMount

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ModuleNotFoundError:
    exit("fuse module not found, please install fusepy to mount images "
             "(`{} install https://github.com/billziss-gh/fusepy/archive/windows.zip`).".format(_common.pip_command))
except Exception as e:
    exit("Failed to import the fuse module:\n"
             "{}: {}".format(type(e).__name__, e))

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ModuleNotFoundError:
    exit("Cryptodome module not found, please install pycryptodomex for encryption support "
             "(`{} install pycryptodomex`).".format(_common.pip_command))
except Exception as e:
    exit("Failed to import the Cryptodome module:\n"
             "{}: {}".format(type(e).__name__, e))


# based on http://stackoverflow.com/questions/1766535/bit-hack-round-off-to-multiple-of-8/1766566#1766566
def new_offset(x: int) -> int:
    return ((x + 63) >> 6) << 6  # - x


class CTRImportableArchiveMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, cia_fp: BinaryIO, dev: bool, g_stat: os.stat_result, seeddb: bool = None):
        self.crypto = CTRCrypto(is_dev=dev)

        self.crypto.setup_keys_from_boot9()

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
        content_offset = tmd_offset + new_offset(tmd_size)
        meta_offset = content_offset + new_offset(content_size)

        # load tmd
        cia_fp.seek(tmd_offset)
        tmd = TitleMetadataReader.load(self.f)
        self.title_id = tmd.title_id

        # read title id, encrypted titlekey and common key index
        cia_fp.seek(ticket_offset + 0x1DC)
        tik_title_id = cia_fp.read(8)
        cia_fp.seek(ticket_offset + 0x1BF)
        enc_titlekey = cia_fp.read(0x10)
        cia_fp.seek(ticket_offset + 0x1F1)
        common_key_index = ord(cia_fp.read(1))

        # decrypt titlekey
        self.crypto.set_keyslot('y', 0x3D, self.crypto.get_common_key(common_key_index))
        titlekey = self.crypto.aes_cbc_decrypt(0x3D, tik_title_id + (b'\0' * 8), enc_titlekey)
        self.crypto.set_normal_key(0x40, titlekey)

        # create virtual files
        self.files = {'/header.bin': {'size': archive_header_size, 'offset': 0, 'type': 'raw'},
                      '/cert.bin': {'size': cert_chain_size, 'offset': cert_chain_offset, 'type': 'raw'},
                      '/ticket.bin': {'size': ticket_size, 'offset': ticket_offset, 'type': 'raw'},
                      '/tmd.bin': {'size': tmd_size, 'offset': tmd_offset, 'type': 'raw'},
                      '/tmdchunks.bin': {'size': tmd.content_count * CHUNK_RECORD_SIZE,
                                         'offset': tmd_offset + 0xB04, 'type': 'raw'}}
        if meta_size:
            self.files['/meta.bin'] = {'size': meta_size, 'offset': meta_offset, 'type': 'raw'}
            # show icon.bin if meta size is the expected size
            # in practice this never changes, but better to be safe
            if meta_size == 0x3AC0:
                self.files['/icon.bin'] = {'size': 0x36C0, 'offset': meta_offset + 0x400, 'type': 'raw'}

        self.dirs = {}

        # read chunks to generate virtual files
        current_offset = content_offset
        for chunk in tmd.chunk_records:
            file_ext = 'nds' if chunk.cindex == b'\0\0' and readbe(self.title_id) >> 44 == 0x48 else 'ncch'
            filename = '/{:04x}.{}.{}'.format(chunk.cindex, chunk.id, file_ext)
            self.files[filename] = {'size': chunk.size, 'offset': current_offset,
                                    'index': chunk.cindex.to_bytes(2, 'big'),
                                    'type': 'enc' if chunk.type.encrypted else 'raw'}
            current_offset += new_offset(chunk.size)

            dirname = '/{:04x}.{}'.format(chunk.cindex, chunk.id)
            try:
                content_vfp = _common.VirtualFileWrapper(self, filename, chunk.size)
                content_fuse = NCCHContainerMount(content_vfp, dev=dev, g_stat=g_stat, seeddb=seeddb)
                self.dirs[dirname] = content_fuse
            except KeyError as e:
                print("Failed to mount {}: {}: {}".format(filename, type(e).__name__, e))

        self.f = cia_fp

    def flush(self, path, fh):
        return self.f.flush()

    def getattr(self, path, fh=None):
        first_dir = _common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].getattr(_common.remove_first_dir(path), fh)
        uid, gid, pid = fuse_get_context()
        if path == '/' or path in self.dirs:
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        elif path.lower() in self.files:
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': self.files[path.lower()]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        first_dir = _common.get_first_dir(path)
        if first_dir in self.dirs:
            yield from self.dirs[first_dir].readdir(_common.remove_first_dir(path), fh)
        yield from ('.', '..')
        yield from (x[1:] for x in self.files)
        yield from (x[1:] for x in self.dirs)

    def read(self, path, size, offset, fh):
        first_dir = _common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].read(_common.remove_first_dir(path), size, offset, fh)
        fi = self.files[path.lower()]
        real_offset = fi['offset'] + offset
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
                iv = fi['index'] + (b'\0' * 14)
            else:
                # use the previous block if reading anywhere else
                self.f.seek(real_offset - before - 0x10)
                iv = self.f.read(0x10)
            # read to block size
            self.f.seek(real_offset - before)
            # adding 0x10 to the size fixes some kind of decryption bug
            data = self.crypto.aes_cbc_decrypt(0x40, iv, self.f.read(size + 0x10))[before:real_size + before]

        else:
            from pprint import pformat
            print('--------------------------------------------------',
                  'Warning: unknown file type (this should not happen!)',
                  'Please file an issue or contact the developer with the details below.',
                  '  https://github.com/ihaveamac/fuse-3ds/issues',
                  '--------------------------------------------------',
                  '{!r}: {!r}'.format(path, pformat(fi)), sep='\n')

            data = b'g' * size

        return data

    def statfs(self, path):
        first_dir = _common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].statfs(_common.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.cia_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


def main():
    parser = ArgumentParser(description="Mount Nintendo 3DS CTR Importable Archive files.",
                            parents=(_common.default_argp, _common.dev_argp, _common.seeddb_argp,
                                              _common.main_positional_args('cia', "CIA file")))

    a = parser.parse_args()
    opts = dict(_common.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    cia_stat = os.stat(a.cia)

    with open(a.cia, 'rb') as f:
        mount = CTRImportableArchiveMount(cia_fp=f, dev=a.dev, g_stat=cia_stat, seeddb=a.seeddb)
        if _common.macos or _common.windows:
            opts['fstypename'] = 'CIA'
            if _common.macos:
                opts['volname'] = "CTR Importable Archive ({})".format(mount.title_id.upper())
            elif _common.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = "CIA ({})".format(mount.title_id.upper())
        fuse = FUSE(mount, a.mount_point, foreground=a.fg or a.do, ro=True, nothreads=True,
                    fsname=os.path.realpath(a.cia).replace(',', '_'), **opts)


if __name__ == '__main__':
    main()
