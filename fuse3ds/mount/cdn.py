#!/usr/bin/env python3

"""
Mounts raw CDN contents, creating a virtual filesystem of decrypted contents (if encrypted).
"""

import argparse
import errno
import hashlib
import logging
import os
import stat
import struct
import sys

from . import common
from pyctr import crypto, util
from .ncch import NCCHContainerMount

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ModuleNotFoundError:
    sys.exit("fuse module not found, please install fusepy to mount images "
             "(`{} install https://github.com/billziss-gh/fusepy/archive/windows.zip`).".format(common.pip_command))
except Exception as e:
    sys.exit("Failed to import the fuse module:\n"
             "{}: {}".format(type(e).__name__, e))

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ModuleNotFoundError:
    sys.exit("Cryptodome module not found, please install pycryptodomex for encryption support "
             "(`{} install pycryptodomex`).".format(common.pip_command))
except Exception as e:
    sys.exit("Failed to import the Cryptodome module:\n"
             "{}: {}".format(type(e).__name__, e))


class CDNContentsMount(LoggingMixIn, Operations):
    fd = 0

    # get the real path by returning self.cdn_dir + path
    def rp(self, path):
        return os.path.join(self.cdn_dir, path)

    def __init__(self, cdn_dir, dev, dec_key=None, seeddb=None):
        self.cdn_dir = cdn_dir

        self.crypto = crypto.CTRCrypto(is_dev=dev)

        self.crypto.setup_keys_from_boot9()

        # get status change, modify, and file access times
        cdn_stat = os.stat(cdn_dir)
        self.g_stat = {'st_ctime': int(cdn_stat.st_ctime), 'st_mtime': int(cdn_stat.st_mtime),
                       'st_atime': int(cdn_stat.st_atime)}

        if not os.path.isfile(self.rp('tmd')):
            sys.exit('tmd not found.')

        with open(self.rp('tmd'), 'rb') as tmd:
            # get title and content count
            tmd.seek(0x18C)
            self.title_id = tmd.read(8)
            tmd.seek(0x1DE)
            content_count = util.readbe(tmd.read(2))
            tmd_chunks_size = content_count * 0x30

            tmd.seek(0xB04)
            tmd_chunks_raw = tmd.read(tmd_chunks_size)

        if not os.path.isfile(self.rp('cetk')):
            if not dec_key:
                sys.exit('cetk not found. Provide the ticket or decrypted titlekey with --dec-key.')

        if dec_key:
            try:
                self.titlekey = bytes.fromhex(dec_key)
                if len(self.titlekey) != 16:
                    sys.exit('--dec-key input is not 32 hex characters.')
            except ValueError:
                sys.exit('Failed to convert --dec-key input to bytes. Non-hex character likely found, or is not '
                         '32 hex characters.')
        else:
            with open(self.rp('cetk'), 'rb') as tik:
                # read encrypted titlekey and common key index
                tik.seek(0x1BF)
                enc_titlekey = tik.read(0x10)
                tik.seek(0x1F1)
                common_key_index = ord(tik.read(1))

            # decrypt titlekey
            self.crypto.set_keyslot('y', 0x3D, self.crypto.get_common_key(common_key_index))
            titlekey = self.crypto.aes_cbc_decrypt(0x3D, self.title_id + (b'\0' * 8), enc_titlekey)
            self.crypto.set_normal_key(0x40, titlekey)

        # create virtual files
        self.files = {'/ticket.bin': {'size': 0x350, 'offset': 0, 'type': 'raw', 'real_filepath': self.rp('cetk')},
                      '/tmd.bin': {'size': 0xB04 + tmd_chunks_size, 'offset': 0, 'type': 'raw',
                                   'real_filepath': self.rp('tmd')},
                      '/tmdchunks.bin': {'size': tmd_chunks_size, 'offset': 0xB04, 'type': 'raw',
                                         'real_filepath': self.rp('tmd')}}

        self.dirs = {}

        # read contents to generate virtual files
        self.cdn_content_size = 0
        for chunk in [tmd_chunks_raw[i:i + 30] for i in range(0, tmd_chunks_size, 0x30)]:
            content_id = chunk[0:4]
            content_index = chunk[4:6]
            if os.path.isfile(self.rp(content_id.hex())):
                real_filename = content_id.hex()
            elif os.path.isfile(self.rp(content_id.hex().upper())):
                real_filename = content_id.hex().upper()
            else:
                print("Content {}:{} not found, will not be included.".format(content_index.hex(), content_id.hex()))
                continue
            content_size = util.readbe(chunk[8:16])
            filesize = os.path.getsize(self.rp(real_filename))
            if content_size != filesize:
                print("Warning: TMD Content size and filesize of {} are different.".format(content_id.hex()))
            self.cdn_content_size += content_size
            content_is_encrypted = util.readbe(chunk[6:8]) & 1
            file_ext = 'nds' if content_index == b'\0\0' and util.readbe(self.title_id) >> 44 == 0x48 else 'ncch'
            filename = '/{}.{}.{}'.format(content_index.hex(), content_id.hex(), file_ext)
            self.files[filename] = {'size': content_size, 'offset': 0, 'index': content_index,
                                    'type': 'enc' if content_is_encrypted else 'raw',
                                    'real_filepath': self.rp(real_filename)}

            dirname = '/{}.{}'.format(content_index.hex(), content_id.hex())
            try:
                content_vfp = common.VirtualFileWrapper(self, filename, content_size)
                content_fuse = NCCHContainerMount(content_vfp, dev=dev, g_stat=cdn_stat, seeddb=seeddb)
                self.dirs[dirname] = content_fuse
            except Exception as e:
                print("Failed to mount {}: {}: {}".format(filename, type(e).__name__, e))

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
        # TODO: maybe this should actually open the file. this isn't so easy
        #   because filenames are being changed in the mount. so right now,
        #   files are opened each time read is called.
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
        with open(fi['real_filepath'], 'rb') as f:
            if fi['type'] == 'raw':
                # if raw, just read and return
                f.seek(real_offset)
                data = f.read(size)

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
                    f.seek(real_offset - before - 0x10)
                    iv = f.read(0x10)
                # read to block size
                f.seek(real_offset - before)
                # adding 0x10 to the size fixes some kind of decryption bug
                data = self.crypto.aes_cbc_decrypt(0x40, iv, f.read(size + 0x10))[before:real_size + before]

            return data

    def statfs(self, path):
        first_dir = common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].read(common.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.cdn_content_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


def main():
    parser = argparse.ArgumentParser(description="Mount Nintendo 3DS CDN contents.", parents=[common.default_argparser])
    parser.add_argument('--dec-key', help="decrypted titlekey")
    parser.add_argument('--dev', help="use dev keys", action='store_const', const=1, default=0)
    parser.add_argument('--seeddb', help="path to seeddb.bin")
    parser.add_argument('cdn_dir', help="directory with CDN contents")
    parser.add_argument('mount_point', help="mount point")

    a = parser.parse_args()
    opts = dict(common.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    mount = CDNContentsMount(cdn_dir=a.cdn_dir, dev=a.dev, dec_key=a.dec_key, seeddb=a.seeddb)
    if common.macos or common.windows:
        opts['fstypename'] = 'CDN'
        opts['volname'] = "CDN Contents ({})".format(mount.title_id.hex().upper())
    fuse = FUSE(mount, a.mount_point, foreground=a.fg or a.do, ro=True, nothreads=True,
                fsname=os.path.realpath(a.cdn_dir).replace(',', '_'), **opts)


if __name__ == '__main__':
    main()
