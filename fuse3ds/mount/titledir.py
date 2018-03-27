#!/usr/bin/env python3

"""
Mounts a "title" directory, creating a virtual system of all the installed titles inside it.
"""

import logging
import os
from argparse import ArgumentParser
from errno import ENOENT
from glob import glob
from stat import S_IFDIR
from sys import exit, argv
from typing import Dict

from pyctr.smdh import SMDH, SMDH_SIZE, InvalidSMDHError
from pyctr.tmd import TitleMetadataReader, CHUNK_RECORD_SIZE

from . import _common as _c
from .ncch import NCCHContainerMount

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ModuleNotFoundError:
    exit("fuse module not found, please install fusepy to mount images "
         "(`{} -mpip install https://github.com/billziss-gh/fusepy/archive/windows.zip`).".format(_c.python_cmd))
except Exception as e:
    exit("Failed to import the fuse module:\n"
         "{}: {}".format(type(e).__name__, e))

_region_order_check = ('English', 'Japanese', 'French', 'German', 'Italian', 'Spanish', 'Simplified Chinese', 'Korean',
                       'Dutch', 'Portuguese', 'Russian', 'Traditional Chinese',)


class TitleDirectoryMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, titles_dir: str, mount_all: bool = False, decompress_code: bool = False, dev: bool = False,
                 seeddb: str = None):
        self.titles_dir = titles_dir
        self.files = {}
        self.dirs = {}  # type: Dict[str, NCCHContainerMount]
        self._real_dir_names = {}  # type: Dict[str, str]

        self.mount_all = mount_all
        self.dev = dev
        self.seeddb = seeddb
        self.total_size = 0

        self.decompress_code = decompress_code

        titles_stat = os.stat(titles_dir)
        self.g_stat = {'st_ctime': int(titles_stat.st_ctime), 'st_mtime': int(titles_stat.st_mtime),
                       'st_atime': int(titles_stat.st_atime)}

    def init(self, path):
        print('Searching for all tmds...')
        tmds = glob(os.path.join(self.titles_dir, '**/{}.tmd'.format('[0-9a-f]' * 8)), recursive=True)
        tmd_count = len(tmds)
        for idx, tmd_path in enumerate(tmds, 1):
            print('Checking... {:>3} / {:>3} / {}'.format(idx, tmd_count, tmd_path), flush=True)
            try:
                tmd = TitleMetadataReader.from_file(tmd_path)
            except Exception as e:
                print('Failed to read {}: {}: {}'.format(tmd_path, type(e).__name__, e))
                continue

            self.total_size = 0
            for chunk in tmd.chunk_records:
                content_path = os.path.dirname(tmd_path)
                if os.path.isfile(os.path.join(content_path, chunk.id + '.app')):
                    real_filename = os.path.join(content_path, chunk.id + '.app')
                elif os.path.isfile(os.path.join(content_path, chunk.id.upper() + '.APP')):
                    real_filename = os.path.join(content_path, chunk.id.upper() + '.APP')
                else:
                    print("Content {0.title_id}:{1.cindex:04}:{1.id} not found, "
                          "will not be included.".format(tmd, chunk))
                    continue
                f_stat = os.stat(real_filename)
                if chunk.size != f_stat.st_size:
                    print("Warning: TMD Content size and filesize of", chunk.id, "are different.")
                file_ext = 'nds' if chunk.cindex == 0 and int(tmd.title_id, 16) >> 44 == 0x48 else 'ncch'
                filename = '/{}.{:04x}.{}.{}'.format(tmd.title_id, chunk.cindex, chunk.id, file_ext)
                self.files[filename] = {'size': chunk.size, 'index': chunk.cindex.to_bytes(2, 'big'),
                                        'real_filepath': real_filename}

                dirname = '/{}.{:04x}.{}'.format(tmd.title_id, chunk.cindex, chunk.id)
                try:
                    content_vfp = _c.VirtualFileWrapper(self, filename, chunk.size)
                    # noinspection PyTypeChecker
                    content_fuse = NCCHContainerMount(content_vfp, decompress_code=self.decompress_code, dev=self.dev,
                                                      g_stat=f_stat, seeddb=self.seeddb)
                    content_fuse.init(path)
                except Exception as e:
                    print("Failed to mount {}: {}: {}".format(real_filename, type(e).__name__, e))
                else:
                    self.total_size += chunk.size
                    try:
                        # noinspection PyTypeChecker
                        smdh = SMDH.load(_c.VirtualFileWrapper(content_fuse.exefs_fuse, '/icon.bin', SMDH_SIZE))
                    except (AttributeError, InvalidSMDHError):
                        pass
                    except FuseOSError as e:
                        if e.args[0] == ENOENT:
                            pass
                        else:
                            print('Unexpected Exception when loading SMDH: {}: {}'.format(type(e).__name__, e))
                    else:
                        for x in _region_order_check:
                            try:
                                dirname += ' ' + smdh.names[x].short_desc
                                break
                            except (AttributeError, TypeError):
                                pass
                    self.dirs[dirname] = content_fuse
                    self._real_dir_names[dirname.lower()] = dirname

                if self.mount_all is False:
                    break

        print('Done!')

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        first_dir = _c.get_first_dir(path)
        if first_dir in self._real_dir_names:
            return self.dirs[self._real_dir_names[first_dir]].getattr(_c.remove_first_dir(path), fh)
        uid, gid, pid = fuse_get_context()
        if path == '/' or path in self.dirs:
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        else:
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        # TODO: maybe this should actually open the file. this isn't so easy
        #   because filenames are being changed in the mount. so right now,
        #   files are opened each time read is called.
        self.fd += 1
        return self.fd

    @_c.ensure_lower_path
    def readdir(self, path, fh):
        first_dir = _c.get_first_dir(path)
        if first_dir in self._real_dir_names:
            yield from self.dirs[self._real_dir_names[first_dir]].readdir(_c.remove_first_dir(path), fh)
        else:
            yield from ('.', '..')
            yield from (x[1:] for x in self.dirs)
            # we do not show self.files, that's just used for internal handling

    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        first_dir = _c.get_first_dir(path)
        if first_dir in self._real_dir_names:
            return self.dirs[self._real_dir_names[first_dir]].read(_c.remove_first_dir(path), size, offset, fh)
        # file handling only to support the above.
        fi = self.files[path]
        with open(fi['real_filepath'], 'rb') as f:
            f.seek(offset)
            return f.read(size)

    @_c.ensure_lower_path
    def statfs(self, path):
        first_dir = _c.get_first_dir(path)
        if first_dir in self._real_dir_names:
            return self.dirs[self._real_dir_names[first_dir]].read(_c.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.total_size // 4096, 'f_bavail': 0, 'f_bfree': 0, 'f_files': 0}


def main(prog: str = None, args: list = None):
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description="Mount Nintendo 3DS NCCH files from installed NAND/SD titles.",
                            parents=(_c.default_argp, _c.dev_argp, _c.seeddb_argp,
                                     _c.main_positional_args('title_dir', "title directory")))
    parser.add_argument('--mount-all', help='mount all contents, not just the first', action='store_true')
    parser.add_argument('--decompress-code', help='decompress code of all mounted titles '
                                                  '(can be slow with lots of titles!)', action='store_true')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    mount = TitleDirectoryMount(titles_dir=a.title_dir, mount_all=a.mount_all, decompress_code=a.decompress_code,
                                dev=a.dev, seeddb=a.seeddb)
    if _c.macos or _c.windows:
        opts['fstypename'] = 'Titles'
        if _c.macos:
            path_to_show = os.path.realpath(a.title_dir).rsplit('/', maxsplit=2)
            opts['volname'] = "Nintendo 3DS Titles Directory ({}/{})".format(path_to_show[-2], path_to_show[-1])
        elif _c.windows:
            # volume label can only be up to 32 chars
            opts['volname'] = "Nintendo 3DS Titles Directory"
    FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=True, nothreads=True, debug=a.d,
         fsname=os.path.realpath(a.title_dir).replace(',', '_'), **opts)


if __name__ == '__main__':
    print('Note: You should be calling this script as "mount_{0}" or "{1} -mfuse3ds {0}" '
          'instead of calling it directly.'.format('titledir', _c.python_cmd))
    main()
