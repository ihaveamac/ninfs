# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts raw CDN contents, creating a virtual filesystem of decrypted contents (if encrypted).
"""

import logging
import os
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import exit, argv
from typing import TYPE_CHECKING

from pyctr.crypto import CryptoEngine, Keyslot, load_seeddb, add_seed
from pyctr.type.ncch import NCCHReader
from pyctr.type.tmd import TitleMetadataReader, CHUNK_RECORD_SIZE

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, load_custom_boot9, \
    realpath
from .ncch import NCCHContainerMount
from .srl import SRLMount

if TYPE_CHECKING:
    from typing import Dict


class CDNContentsMount(LoggingMixIn, Operations):
    fd = 0

    # get the real path by returning self.cdn_dir + path
    def rp(self, path):
        return os.path.join(self.cdn_dir, path)

    def __init__(self, tmd_file: str = None, cdn_dir: str = None, dec_key: str = None, dev: bool = False,
                 boot9: str = None, seed: str = None):
        if tmd_file:
            self.cdn_dir = os.path.dirname(tmd_file)
        else:
            self.cdn_dir = cdn_dir
            tmd_file = os.path.join(cdn_dir, 'tmd')

        self.crypto = CryptoEngine(boot9=boot9, dev=dev)

        self.cdn_content_size = 0
        self.dev = dev

        # get status change, modify, and file access times
        try:
            self.g_stat = get_time(tmd_file)
        except FileNotFoundError:
            exit('Could not find "tmd" in directory')

        self.tmd = TitleMetadataReader.from_file(tmd_file)

        # noinspection PyUnboundLocalVariable
        self.title_id = self.tmd.title_id

        if seed:
            add_seed(self.title_id, seed)

        if not os.path.isfile(self.rp('cetk')):
            if not dec_key:
                exit('cetk not found. Provide the ticket or decrypted titlekey with --dec-key.')

        if dec_key:
            try:
                titlekey = bytes.fromhex(dec_key)
                if len(titlekey) != 16:
                    exit('--dec-key input is not 32 hex characters.')
            except ValueError:
                exit('Failed to convert --dec-key input to bytes. Non-hex character likely found, or is not '
                     '32 hex characters.')
            # noinspection PyUnboundLocalVariable
            self.crypto.set_normal_key(Keyslot.DecryptedTitlekey, titlekey)
        else:
            with open(self.rp('cetk'), 'rb') as tik:
                # load ticket
                self.crypto.load_from_ticket(tik.read(0x350))

        # create virtual files
        self.files = {'/ticket.bin': {'size': 0x350, 'type': 'raw', 'real_filepath': self.rp('cetk')},
                      '/tmd.bin': {'size': 0xB04 + self.tmd.content_count * CHUNK_RECORD_SIZE, 'offset': 0,
                                   'type': 'raw', 'real_filepath': self.rp('tmd')},
                      '/tmdchunks.bin': {'size': self.tmd.content_count * CHUNK_RECORD_SIZE, 'offset': 0xB04,
                                         'type': 'raw', 'real_filepath': self.rp('tmd')}}

        self.dirs: Dict[str, NCCHContainerMount] = {}

    def init(self, path):
        # read contents to generate virtual files
        for chunk in self.tmd.chunk_records:
            if os.path.isfile(self.rp(chunk.id)):
                real_filename = chunk.id
            elif os.path.isfile(self.rp(chunk.id.upper())):
                real_filename = chunk.id.upper()
            else:
                print(f'Content {chunk.cindex:04}:{chunk.id} not found, will not be included.')
                continue
            f_stat = os.stat(self.rp(real_filename))
            if chunk.size != f_stat.st_size:
                print('Warning: TMD Content size and filesize of', chunk.id, 'are different.')
            self.cdn_content_size += chunk.size
            is_srl = chunk.cindex == 0 and self.title_id[3:5] == '48'
            file_ext = 'nds' if is_srl else 'ncch'
            filename = f'/{chunk.cindex:04x}.{chunk.id}.{file_ext}'
            self.files[filename] = {'size': chunk.size, 'index': chunk.cindex.to_bytes(2, 'big'),
                                    'type': 'enc' if chunk.type.encrypted else 'raw',
                                    'real_filepath': self.rp(real_filename)}

            dirname = f'/{chunk.cindex:04x}.{chunk.id}'
            # noinspection PyBroadException
            try:
                f_time = get_time(f_stat)
                content_vfp = _c.VirtualFileWrapper(self, filename, chunk.size)
                # boot9 is not passed here, as CryptoEngine has already set up the keys at the beginning.
                if is_srl:
                    content_fuse = SRLMount(content_vfp, g_stat=f_time)
                else:
                    content_reader = NCCHReader(content_vfp, dev=self.dev)
                    content_fuse = NCCHContainerMount(content_reader, g_stat=f_time)
                content_fuse.init(path)
                self.dirs[dirname] = content_fuse
            except Exception as e:
                print(f'Failed to mount {filename}: {type(e).__name__}: {e}')

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
        real_size = size
        with open(fi['real_filepath'], 'rb') as f:
            if fi['type'] == 'raw':
                # if raw, just read and return
                f.seek(offset)
                data = f.read(size)

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
                    f.seek(offset - before - 0x10)
                    iv = f.read(0x10)
                # read to block size
                f.seek(offset - before)
                # adding 0x10 to the size fixes some kind of decryption bug
                data = self.crypto.create_cbc_cipher(Keyslot.DecryptedTitlekey,
                                                     iv).decrypt(f.read(size + 0x10))[before:real_size + before]

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
            return self.dirs[first_dir].read(_c.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.cdn_content_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS CDN contents.',
                            parents=(_c.default_argp, _c.ctrcrypto_argp, _c.seeddb_argp,
                                     _c.main_args('content', 'tmd file or directory with CDN contents')))
    parser.add_argument('--dec-key', help='decrypted titlekey')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    mount_opts = {}
    if os.path.isfile(a.content):
        mount_opts['tmd_file'] = a.content
    else:
        mount_opts['cdn_dir'] = a.content

    load_custom_boot9(a.boot9)

    if a.seeddb:
        load_seeddb(a.seeddb)

    mount = CDNContentsMount(dev=a.dev, dec_key=a.dec_key, boot9=a.boot9, seed=a.seed, **mount_opts)
    if _c.macos or _c.windows:
        opts['fstypename'] = 'CDN'
        opts['volname'] = f'CDN Contents ({mount.title_id.upper()})'
    FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
         fsname=realpath(a.content).replace(',', '_'), **opts)
