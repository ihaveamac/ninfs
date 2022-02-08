# This file is a part of ninfs.
#
# Copyright (c) 2017-2021 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts Executable Filesystem (ExeFS) files, creating a virtual filesystem of the ExeFS contents.
"""

import logging
from errno import ENOENT
from itertools import chain
from io import BytesIO
from stat import S_IFDIR, S_IFREG
from sys import argv
from threading import Lock
from typing import TYPE_CHECKING

import png
from pyctr.type.exefs import ExeFSReader, ExeFSFileNotFoundError, CodeDecompressionError
from pyctr.type.smdh import SMDH, InvalidSMDHError

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, realpath

if TYPE_CHECKING:
    from typing import BinaryIO, Dict, Union


class ExeFSMount(LoggingMixIn, Operations):
    fd = 0
    files: 'Dict[str, str]'
    special_files: 'Dict[str, Dict[str, Union[int, BinaryIO]]]'

    def __init__(self, reader: 'ExeFSReader', g_stat: dict, decompress_code: bool = False):
        self.g_stat = g_stat

        self.reader = reader
        self.decompress_code = decompress_code

        self.special_files_lock = Lock()

        # for vfs stats
        self.exefs_size = sum(x.size for x in self.reader.entries.values())

    def __del__(self, *args):
        try:
            self.reader.close()
        except AttributeError:
            pass

        with self.special_files_lock:
            for f in self.special_files.values():
                f['io'].close()

    destroy = __del__

    # TODO: maybe do this in a way that allows for multiprocessing (titledir)
    def init(self, path, data=None):
        if self.decompress_code and '.code' in self.reader.entries:
            print('ExeFS: Decompressing code...')
            try:
                res = self.reader.decompress_code()
            except CodeDecompressionError as e:
                print(f'ExeFS: Failed to decompress code: {e}')
            else:
                if res:
                    print('ExeFS: Done!')
                else:
                    print('ExeFS: No decompression needed')

        # displayed name associated with real entry name
        self.files = {'/' + x.name.replace('.', '', 1) + '.bin': x.name for x in self.reader.entries.values()}
        self.special_files = {}

        if self.reader.icon:
            icon_small = BytesIO()
            icon_large = BytesIO()

            def load_to_pypng(array, w, h):
                return png.from_array((chain.from_iterable(x) for x in array), 'RGB', {'width': w, 'height': h})

            load_to_pypng(self.reader.icon.icon_small_array, 24, 24).write(icon_small)
            load_to_pypng(self.reader.icon.icon_large_array, 48, 48).write(icon_large)

            icon_small_size = icon_small.seek(0, 2)
            icon_large_size = icon_large.seek(0, 2)

            # these names are too long to be in the exefs, so special checks can be added for them
            self.special_files['/icon_small.png'] = {'size': icon_small_size, 'io': icon_small}
            self.special_files['/icon_large.png'] = {'size': icon_large_size, 'io': icon_large}

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        if path == '/':
            st = {'st_mode': (S_IFDIR | 0o777), 'st_nlink': 2}
        else:
            if path in self.files:
                item = self.reader.entries[self.files[path]]
                size = item.size
            elif path in self.special_files:
                item = self.special_files[path]
                size = item['size']
            else:
                raise FuseOSError(ENOENT)
            st = {'st_mode': (S_IFREG | 0o666), 'st_size': size, 'st_nlink': 1}
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    @_c.ensure_lower_path
    def readdir(self, path, fh):
        yield from ('.', '..')
        yield from (x[1:] for x in self.files)
        yield from (x[1:] for x in self.special_files)

    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        if path in self.files:
            with self.reader.open(self.files[path]) as f:
                f.seek(offset)
                return f.read(size)
        elif path in self.special_files:
            with self.special_files_lock:
                f = self.special_files[path]['io']
                f.seek(offset)
                return f.read(size)
        else:
            raise FuseOSError(ENOENT)

    @_c.ensure_lower_path
    def statfs(self, path):
        return {'f_bsize': 4096, 'f_frsize': 4096, 'f_blocks': self.exefs_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.reader) + len(self.special_files)}


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS Executable Filesystem (ExeFS) files.',
                            parents=(_c.default_argp, _c.main_args('exefs', 'ExeFS file')))
    parser.add_argument('--decompress-code', help='decompress the .code section', action='store_true')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    exefs_stat = get_time(a.exefs)

    with ExeFSReader(a.exefs) as r:
        mount = ExeFSMount(reader=r, g_stat=exefs_stat, decompress_code=a.decompress_code)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'ExeFS'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            path_to_show = realpath(a.exefs).rsplit('/', maxsplit=2)
            if _c.macos:
                opts['volname'] = f'Nintendo 3DS ExeFS ({path_to_show[-2]}/{path_to_show[-1]})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = 'Nintendo 3DS ExeFS'
        FUSE(mount, a.mount_point, foreground=a.fg or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=realpath(a.exefs).replace(',', '_'), **opts)
