#!/usr/bin/env python3

"""
Mounts raw CDN contents, creating a virtual filesystem of decrypted contents (if encrypted).
"""

from argparse import ArgumentParser
from errno import ENOENT
import logging
import os
from stat import S_IFDIR, S_IFREG
from sys import exit

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


class CDNContentsMount(LoggingMixIn, Operations):
    fd = 0

    # get the real path by returning self.cdn_dir + path
    def rp(self, path):
        return os.path.join(self.cdn_dir, path)

    def __init__(self, cdn_dir, dev, dec_key=None, seeddb=None):
        self.cdn_dir = cdn_dir

        self.crypto = CTRCrypto(is_dev=dev)
        self.crypto.setup_keys_from_boot9()

        # get status change, modify, and file access times
        cdn_stat = os.stat(cdn_dir)
        self.g_stat = {'st_ctime': int(cdn_stat.st_ctime), 'st_mtime': int(cdn_stat.st_mtime),
                       'st_atime': int(cdn_stat.st_atime)}

        try:
            tmd = TitleMetadataReader.from_file(self.rp('tmd'))
        except FileNotFoundError:
            exit('tmd not found.')
        
        self.title_id = tmd.title_id

        if not os.path.isfile(self.rp('cetk')):
            if not dec_key:
                exit('cetk not found. Provide the ticket or decrypted titlekey with --dec-key.')

        if dec_key:
            try:
                self.titlekey = bytes.fromhex(dec_key)
                if len(self.titlekey) != 16:
                    exit('--dec-key input is not 32 hex characters.')
            except ValueError:
                exit('Failed to convert --dec-key input to bytes. Non-hex character likely found, or is not '
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
            titlekey = self.crypto.aes_cbc_decrypt(0x3D, bytes.fromhex(self.title_id) + (b'\0' * 8), enc_titlekey)
            self.crypto.set_normal_key(0x40, titlekey)

        # create virtual files
        self.files = {'/ticket.bin': {'size': 0x350, 'offset': 0, 'type': 'raw', 'real_filepath': self.rp('cetk')},
                      '/tmd.bin': {'size': 0xB04 + tmd.content_count * CHUNK_RECORD_SIZE, 'offset': 0, 'type': 'raw',
                                   'real_filepath': self.rp('tmd')},
                      '/tmdchunks.bin': {'size': tmd.content_count * CHUNK_RECORD_SIZE, 'offset': 0xB04, 'type': 'raw',
                                         'real_filepath': self.rp('tmd')}}

        self.dirs = {}

        # read contents to generate virtual files
        self.cdn_content_size = 0
        for chunk in tmd.chunk_records:
            if os.path.isfile(self.rp(chunk.id)):
                real_filename = chunk.id
            elif os.path.isfile(self.rp(chunk.id.upper())):
                real_filename = chunk.id.upper()
            else:
                print("Content {}:{} not found, will not be included.".format(chunk.cindex, chunk.id))
                continue
            filesize = os.path.getsize(self.rp(real_filename))
            if chunk.size != filesize:
                print("Warning: TMD Content size and filesize of", chunk.id, "are different.")
            self.cdn_content_size += chunk.size
            file_ext = 'nds' if chunk.cindex == 0 and int(self.title_id, 16) >> 44 == 0x48 else 'ncch'
            filename = '/{:04x}.{}.{}'.format(chunk.cindex, chunk.id, file_ext)
            self.files[filename] = {'size': chunk.size, 'offset': 0, 'index': chunk.cindex.to_bytes(2, 'big'),
                                    'type': 'enc' if chunk.type.encrypted else 'raw',
                                    'real_filepath': self.rp(real_filename)}

            dirname = '/{:04x}.{}'.format(chunk.cindex, chunk.id)
            try:
                content_vfp = _common.VirtualFileWrapper(self, filename, chunk.size)
                content_fuse = NCCHContainerMount(content_vfp, dev=dev, g_stat=cdn_stat, seeddb=seeddb)
                self.dirs[dirname] = content_fuse
            except Exception as e:
                print("Failed to mount {}: {}: {}".format(filename, type(e).__name__, e))

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
        # TODO: maybe this should actually open the file. this isn't so easy
        #   because filenames are being changed in the mount. so right now,
        #   files are opened each time read is called.
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        first_dir = _common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].readdir(_common.remove_first_dir(path), fh)
        return ['.', '..'] + [x[1:] for x in self.files] + [x[1:] for x in self.dirs]

    def read(self, path, size, offset, fh):
        first_dir = _common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].read(_common.remove_first_dir(path), size, offset, fh)
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
        first_dir = _common.get_first_dir(path)
        if first_dir in self.dirs:
            return self.dirs[first_dir].read(_common.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.cdn_content_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


def main():
    parser = ArgumentParser(description="Mount Nintendo 3DS CDN contents.",
                            parents=(_common.default_argp, _common.dev_argp, _common.seeddb_argp,
                                              _common.main_positional_args('cdn_dir', "directory with CDN contents")))
    parser.add_argument('--dec-key', help="decrypted titlekey")

    a = parser.parse_args()
    opts = dict(_common.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    mount = CDNContentsMount(cdn_dir=a.cdn_dir, dev=a.dev, dec_key=a.dec_key, seeddb=a.seeddb)
    if _common.macos or _common.windows:
        opts['fstypename'] = 'CDN'
        opts['volname'] = "CDN Contents ({})".format(mount.title_id.upper())
    fuse = FUSE(mount, a.mount_point, foreground=a.fg or a.do, ro=True, nothreads=True,
                fsname=os.path.realpath(a.cdn_dir).replace(',', '_'), **opts)


if __name__ == '__main__':
    main()
