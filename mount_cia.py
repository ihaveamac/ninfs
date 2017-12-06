#!/usr/bin/env python3

import argparse
import errno
import hashlib
import logging
import os
import stat
import struct
import sys

import common
from pyctr import crypto, util

try:
    from mount_ncch import NCCHContainerMount
except ImportError:
    print("Failed to import import_ncch, NCCH mount will not be available.")
    NCCHContainerMount = None

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


# based on http://stackoverflow.com/questions/1766535/bit-hack-round-off-to-multiple-of-8/1766566#1766566
def new_offset(x: int) -> int:
    return ((x + 63) >> 6) << 6  # - x


class CTRImportableArchiveMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, cia_fp, dev, g_stat, seeddb=None):
        self.crypto = crypto.CTRCrypto(is_dev=dev)

        self.crypto.setup_keys_from_boot9()

        # get status change, modify, and file access times
        self.g_stat = {'st_ctime': int(g_stat.st_ctime), 'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        # open cia and get section sizes
        self.f = cia_fp
        archive_header_size, cia_type, cia_version, cert_chain_size, \
            ticket_size, tmd_size, meta_size, content_size = struct.unpack('<IHHIIIIQ', self.f.read(0x20))

        self.cia_size = new_offset(archive_header_size) + new_offset(cert_chain_size) + new_offset(ticket_size)\
            + new_offset(tmd_size) + new_offset(meta_size) + new_offset(content_size)

        # get offsets for sections of the CIA
        # each section is aligned to 64-byte blocks
        cert_chain_offset = new_offset(archive_header_size)
        ticket_offset = cert_chain_offset + new_offset(cert_chain_size)
        tmd_offset = ticket_offset + new_offset(ticket_size)
        content_offset = tmd_offset + new_offset(tmd_size)
        meta_offset = content_offset + new_offset(content_size)

        # read title id, encrypted titlekey and common key index
        self.f.seek(ticket_offset + 0x1DC)
        title_id = self.f.read(8)
        self.f.seek(ticket_offset + 0x1BF)
        enc_titlekey = self.f.read(0x10)
        self.f.seek(ticket_offset + 0x1F1)
        common_key_index = ord(self.f.read(1))

        # decrypt titlekey
        self.crypto.set_keyslot('y', 0x3D, self.crypto.get_common_key(common_key_index))
        titlekey = self.crypto.aes_cbc_decrypt(0x3D, title_id + (b'\0' * 8), enc_titlekey)
        self.crypto.set_normal_key(0x40, titlekey)

        # get content count
        self.f.seek(tmd_offset + 0x1DE)
        content_count = util.readbe(self.f.read(2))

        # get offset for tmd chunks, mostly so it can be put into a tmdchunks.bin virtual file
        tmd_chunks_offset = tmd_offset + 0xB04
        tmd_chunks_size = content_count * 0x30

        # create virtual files
        self.files = {'/header.bin': {'size': archive_header_size, 'offset': 0, 'type': 'raw'},
                      '/cert.bin': {'size': cert_chain_size, 'offset': cert_chain_offset, 'type': 'raw'},
                      '/ticket.bin': {'size': ticket_size, 'offset': ticket_offset, 'type': 'raw'},
                      '/tmd.bin': {'size': tmd_size, 'offset': tmd_offset, 'type': 'raw'},
                      '/tmdchunks.bin': {'size': tmd_chunks_size, 'offset': tmd_chunks_offset, 'type': 'raw'}}
        if meta_size:
            self.files['/meta.bin'] = {'size': meta_size, 'offset': meta_offset, 'type': 'raw'}
            # show icon.bin if meta size is the expected size
            # in practice this never changes, but better to be safe
            if meta_size == 0x3AC0:
                self.files['/icon.bin'] = {'size': 0x36C0, 'offset': meta_offset + 0x400, 'type': 'raw'}

        self.f.seek(tmd_chunks_offset)
        tmd_chunks_raw = self.f.read(tmd_chunks_size)

        self.dirs = {}

        # read chunks to generate virtual files
        current_offset = content_offset
        for chunk in [tmd_chunks_raw[i:i + 30] for i in range(0, content_count * 0x30, 0x30)]:
            content_id = chunk[0:4]
            content_index = chunk[4:6]
            content_size = util.readbe(chunk[8:16])
            content_is_encrypted = util.readbe(chunk[6:8]) & 1
            file_ext = 'nds' if content_index == b'\0\0' and util.readbe(title_id) >> 44 == 0x48 else 'ncch'
            filename = '/{}.{}.{}'.format(content_index.hex(), content_id.hex(), file_ext)
            self.files[filename] = {'size': content_size, 'offset': current_offset, 'index': content_index,
                                    'type': 'enc' if content_is_encrypted else 'raw'}
            current_offset += new_offset(content_size)

            dirname = '/{}.{}'.format(content_index.hex(), content_id.hex())
            try:
                content_vfp = common.VirtualFileWrapper(self, filename, content_size)
                content_fuse = NCCHContainerMount(content_vfp, dev=dev, g_stat=g_stat, seeddb=seeddb)
                self.dirs[dirname] = content_fuse
            except Exception as e:
                print("Failed to mount {}: {}: {}".format(filename, type(e).__name__, e))

    def flush(self, path, fh):
        return self.f.flush()

    def getattr(self, path, fh=None):
        first_dir = common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].getattr(common.remove_first_dir(path), fh)
        uid, gid, pid = fuse_get_context()
        if path == '/' or path in self.dirs:
            st = {'st_mode': (stat.S_IFDIR | 0o555), 'st_nlink': 2}
        elif path.lower() in self.files:
            st = {'st_mode': (stat.S_IFREG | 0o444), 'st_size': self.files[path.lower()]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(errno.ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        first_dir = common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].readdir(common.remove_first_dir(path), fh)
        return ['.', '..'] + [x[1:] for x in self.files] + [x[1:] for x in self.dirs]

    def read(self, path, size, offset, fh):
        first_dir = common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].read(common.remove_first_dir(path), size, offset, fh)
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
            after = (offset + size) % 16
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

        return data

    def statfs(self, path):
        first_dir = common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].statfs(common.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.cia_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS CTR Importable Archive files.')
    parser.add_argument('--dev', help="use dev keys", action='store_const', const=1, default=0)
    parser.add_argument('--seeddb', help="path to seeddb.bin")
    parser.add_argument('--fg', '-f', help="run in foreground", action='store_true')
    parser.add_argument('--do', help="debug output (python logging module)", action='store_true')
    parser.add_argument('-o', metavar='OPTIONS', help="mount options")
    parser.add_argument('cia', help="CIA file")
    parser.add_argument('mount_point', help="mount point")

    a = parser.parse_args()
    try:
        opts = {o: True for o in a.o.split(',')}
    except AttributeError:
        opts = {}

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    cia_stat = os.stat(a.cia)

    with open(a.cia, 'rb') as f:
        fuse = FUSE(CTRImportableArchiveMount(cia_fp=f, dev=a.dev, g_stat=cia_stat, seeddb=a.seeddb), a.mount_point,
                    foreground=a.fg or a.do, fsname=os.path.realpath(a.cia), ro=True, nothreads=True, **opts)
