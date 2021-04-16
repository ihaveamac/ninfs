# This is an example mount for a read-only type (e.g. game contents). This simple mount takes a single file and provides
# a passthroguh for its contents split into two files.

# Everything here is provided as an example that most types use, but there is no one-size-fits-all module.
# Certain aspects of this will need to be modified to fit what the mount type uses.
# Some may use a different system entirely.
# For example, the CDN and SD mounts use a directory, and so can only accept a file path and work from files on disk.

# This all runs in a single thread, enforced by nothreads=True being added to the FUSE call.
# Multithreading is possible if you know how to handle thread locking.

"""
Mirrors the contents of a file in two parts.
"""

import logging
from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import argv
from typing import TYPE_CHECKING, BinaryIO

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, realpath

if TYPE_CHECKING:
    from typing import Dict


class ReadOnlyMount(LoggingMixIn, Operations):
    # File descriptor count. Incremented on each open. See the open method for more details.
    fd = 0

    # File size. This is set in init (not __init__).
    size = 0

    # This is called when a ReadOnlyMount object is created.
    # DON'T PUT HEAVY INITIALIZATION HERE!!! Since this method is always called by Python, it doesn't stop if the mount
    #   fails for any reason (missing directory, no permission, etc.).
    # This should only set up the basics. This can include verifying a file header and setting up a reader.
    def __init__(self, file: BinaryIO, g_stat: dict):
        # The file here is provided as a file-like binary object, rather than a file path. This is highly preferable to
        # accepting a file path, since this means it works with files that do not directly come from the disk
        # (e.g. the contents of a game filesystem).
        self.f = file

        # This hold stat information related to time. Since the file may not come directly from disk, this is created
        # outside the function. Usually if this mount is used inside another, g_stat is taken from the parent mount
        # (e.g. RomFSMount would take g_stat from the NCCHMount that has it).
        # Check the getattr method for more details.
        self.g_stat = g_stat

        # A dict of files at the root. For a simple file type, this could be a list of offsets and sizes.
        # The dict won't actually be generated until init is called.
        self.files: Dict[str, Dict[str, int]] = {}

    def __del__(self, *args):
        # This tries to close the file when the object is destroyed or when the filesystem is closing (which calls
        # destroy). AttributeError is caught in case f or close don't exist, which can happen if it is raised early.
        try:
            self.f.close()
        except AttributeError:
            pass

    # This is called when the filesystem is being unmounted. In nearly all cases this doesn't need to be different to
    # __del__. It returns a "path" argument that is always '/' and can be ignored.
    destroy = __del__

    # This is called when FUSE successfully creates the mount. This is where heavy initialization should go, now that it
    # is guaranteed to be used. It's still possible to raise errors here though, in cases such as the file being
    # corrupted.
    # path is always '/' and can be ignored.
    def init(self, path):
        # The size of the file is obtained by seeking to the end.
        self.size = self.f.seek(0, 2)
        self.f.seek(0)

        # Getting the middle point which will be used as both a size and offset.
        middle = self.size // 2

        # Adding the first half.
        self.files['/first.bin'] = {'offset': 0, 'size': middle}

        # ...and the second half.
        self.files['/second.bin'] = {'offset': middle, 'size': self.size - middle}

    # This is called when a program calls `stat` on the file.
    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        # This gets the user, group, and process IDs of the thread that is making the call. pid is unused here.
        uid, gid, pid = fuse_get_context()

        # If a program is trying to stat the root of the filesystem, it returns a mode equivalent to read+execute.
        # st_nlink is number of hard links. For directories this is 2. (I don't understand how that works...)
        if path == '/':
            st = {'st_mode': (S_IFDIR | 0o555), 'st_nlink': 2}
        # If it's a file within the filesystem, it will try to return the size of it, as well as a mode that only allows
        # reading.
        elif path in self.files:
            st = {'st_mode': (S_IFREG | 0o444), 'st_size': self.files[path]['size'], 'st_nlink': 1}
        # Otherwise raise ENOENT if the file doesn't exist.
        else:
            raise FuseOSError(ENOENT)

        # This includes the stat fields defined above, as well as g_stat which includes st_ctime, st_mtime, and
        # st_atime.
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    # This is called when a request to open a file is made.
    def open(self, path, flags):
        # The actual file descriptor is not important most of the time, so a dummy one is returned.
        # If you want to manage the fd manually, it is returned as "fh" in every other method.
        self.fd += 1
        return self.fd

    # This is called when a request to view the contents of a directory is made.
    @_c.ensure_lower_path
    def readdir(self, path, fh):
        # Return the "current" and "parent" directory parts, since FUSE needs this for some reason.
        yield from ('.', '..')
        # Return each file name without the beginning '/'.
        yield from (x[1:] for x in self.files)

    # This is called when a request to read part of a file is made.
    # There are some platform quirks here. Windows will not check if the offset and size goes beyond the file size.
    # For example, if a Windows program requests 200 bytes, even if the file is 100 bytes, it will still ask for 200.
    # Therefore it is up to you to check and enforce boundaries.
    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        # Get the file information.
        fi = self.files[path]

        # Calculate the offset to read in the base file.
        real_offset = fi['offset'] + offset

        # Check if the requested offset is beyond the file size, and return an empty bytestring if so.
        if fi['offset'] + offset > fi['offset'] + fi['size']:
            return b''

        # Check if the size would go beyond the end, and clamp it to the EoF.
        if offset + size > fi['size']:
            size = fi['size'] - offset

        # Seek to the real offset in the base file and return the requested data.
        self.f.seek(real_offset)
        return self.f.read(size)

    # This is called when the filesystem stats are requested (not the same as stat-ing the root directory).
    def statfs(self, path):
        # This dict has multiple keys that follow `struct statvfs`. This is a simplified version because some of the
        # nuances between different stat fields do not apply to most ninfs types. The full documented version is
        # available here: https://man7.org/linux/man-pages/man3/statvfs.3.html

        # f_bsize and f_frsize: Block size. Most of the time these should be identical.
        # f_blocks: Amount of blocks used.
        # f_bavail and f_bfree: Amount of free blocks. Most of the time these should be identical.
        # f_files: Amount of files and directories. Doesn't seem to affect anything if this doesn't line up with the
        #   actual amount in the filesystem.
        return {'f_bsize': 512, 'f_frsize': 512, 'f_blocks': self.size // 512, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}


# This function is called by ninfs.main. prog is the command used to call ninfs (e.g. mount_readonly), args is a list
#   of arguments. If it doesn't exist, it is taken from sys.argv.
def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]

    # Different sets of pre-defined arguments are included in ninfs.
    # These ones are always required:
    # - _c.default_argp: includes --fg/-f, -d, --do, -o
    # - _c.main_args('argname', 'Description of file type'): adds file input and mount point
    #   'argname' will be used as the object property name containing the file path (e.g. a.argname).

    # These are available:
    #   _c.readonly_argp: adds --ro/-r
    parser = ArgumentParser(prog=prog, description='Show a file split in two.',
                            parents=(_c.default_argp, _c.main_args('myfile', 'Any file')))

    a = parser.parse_args(args)
    # The options given to -o are parsed to be given as arguments to the FUSE class.
    opts = dict(_c.parse_fuse_opts(a.o))

    # Enable fusepy debug logging. This is enabled with `--do <filename>`.
    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    # Get the stat of the file which will be put into g_stat.
    # `get_time` will fall back on default values if os.stat fails due to OSError,
    #   such as on a physical drive on Windows.
    myfile_stat = get_time(a.myfile)

    with open(a.myfile, 'rb') as f:
        # Create the mount object with the opened file object.
        mount = ReadOnlyMount(file=f, g_stat=myfile_stat)
        # Some of these options are exclusive to WinFsp and macFUSE and will raise an error on Linux/BSD.
        if _c.macos or _c.windows:
            # fstypename shows the format of the filesystem.
            # macFUSE will show this as "macfuse_SPLIT"
            # WinFSp will show this as "FUSE-SPLIT".
            opts['fstypename'] = 'SPLIT'
            if _c.macos:
                # macOS allows a long volume name (not sure what the limit is).
                # So for this, the file and its parent directory are included.
                # Something more useful could also be added here, such as some unique ID or a title's name.
                path_to_show = realpath(a.myfile).rsplit('/', maxsplit=2)
                opts['volname'] = f'Split read-only file ({path_to_show[-2]}/{path_to_show[-1]})'
            elif _c.windows:
                # Windows only allows a volume name of up to 32 characters.
                opts['volname'] = 'Split read-only file'

        # This is what starts the mounting process.
        # - foreground means the process will not fork into the background. WinFsp-FUSE always runs in the foreground,
        #   making this option useless on Windows.
        # - ro means the mount is read-only
        # - nothreads means the mount will only run in a single thread, and only one operation can be executing at a
        #   time.
        # - debug enables FUSE's debugging output. This is different from fusepy's debug output and is different
        #   between Linux/BSD/macOS and Windows. If you want to debug your script you should almost certainly use
        #   fusepy's debugging.
        # - fsname appears when `mount` is executed on Linux/BSD/macOS and usually contains the path to the base file.
        #   ',' is replaced with '_' or else some parts will be mistaken as FUSE options.
        FUSE(mount, a.mount_point, foreground=a.fg or a.d, ro=True, nothreads=True, debug=a.d,
             fsname=realpath(a.myfile).replace(',', '_'), **opts)
