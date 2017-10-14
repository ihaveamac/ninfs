#!/usr/bin/env python3

import argparse
import errno
import hashlib
import logging
import os
import stat
import struct
import sys

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ImportError:
    sys.exit('fuse module not found, please install fusepy to mount images (`pip3 install git+https://github.com/billziss-gh/fusepy.git`).')

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ImportError:
    sys.exit('Cryptodome module not found, please install pycryptodomex for encryption support (`pip3 install pycryptodomex`).')


# used from http://www.falatic.com/index.php/108/python-and-bitwise-rotation
# converted to def because pycodestyle complained to me
def rol(val, r_bits, max_bits):
    return (val << r_bits % max_bits) & (2 ** max_bits - 1) | ((val & (2 ** max_bits - 1)) >> (max_bits - (r_bits % max_bits)))


def keygen(key_x, key_y):
    return rol((rol(key_x, 2, 128) ^ key_y) + 0x1FF9E9AAC5FE0408024591DC5D52768A, 87, 128).to_bytes(0x10, 'big')


# these would have to be obtained from Process9 and that's annoying.
common_key_y = (
    ('D07B337F9CA4385932A2E25723232EB9', '85215E96CB95A9ECA4B4DE601CB562C7'),
    ('0C767230F0998F1C46828202FAACBE4C', '0C767230F0998F1C46828202FAACBE4C'),
    ('C475CB3AB8C788BB575E12A10907B8A4', 'C475CB3AB8C788BB575E12A10907B8A4'),
    ('E486EEE3D0C09C902F6686D4C06F649F', 'E486EEE3D0C09C902F6686D4C06F649F'),
    ('ED31BA9C04B067506C4497A35B7804FC', 'ED31BA9C04B067506C4497A35B7804FC'),
    ('5E66998AB4E8931606850FD7A16DD755', '5E66998AB4E8931606850FD7A16DD755')
)


class CDNContents(LoggingMixIn, Operations):
    fd = 0

    # get the real path by returning self.cdn_dir + path
    def rp(self, path):
        return os.path.join(self.cdn_dir, path)

    def __init__(self, cdn_dir, dev, dec_key):
        self.cdn_dir = cdn_dir
        keys_set = False
        key_x = 0

        # check for boot9 to get common key X
        def check_b9_file(path):
            nonlocal keys_set, key_x
            if not keys_set:
                if os.path.isfile(path):
                    key_offset = 0x5A20
                    if dev:
                        key_offset += 0x400
                    if os.path.getsize(path) == 0x10000:
                        key_offset += 0x8000
                    with open(path, 'rb') as b9:
                        b9.seek(key_offset)
                        key_x = int.from_bytes(b9.read(0x10), 'big')
                    keys_set = True

        check_b9_file('boot9.bin')
        check_b9_file('boot9_prot.bin')
        check_b9_file(os.path.expanduser('~') + '/.3ds/boot9.bin')
        check_b9_file(os.path.expanduser('~') + '/.3ds/boot9_prot.bin')

        if not keys_set:
            sys.exit('Failed to get keys from boot9')

        # get status change, modify, and file access times
        cdn_stat = os.stat(cdn_dir)
        self.g_stat = {}
        self.g_stat['st_ctime'] = int(cdn_stat.st_ctime)
        self.g_stat['st_mtime'] = int(cdn_stat.st_mtime)
        self.g_stat['st_atime'] = int(cdn_stat.st_atime)

        if not os.path.isfile(self.rp('tmd')):
            sys.exit('tmd not found.')

        with open(self.rp('tmd'), 'rb') as tmd:
            # get title and content count
            tmd.seek(0x18C)
            title_id = tmd.read(8)
            tmd.seek(0x1DE)
            content_count = int.from_bytes(tmd.read(2), 'big')
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
                sys.exit('Failed to convert --dec-key input to bytes. Non-hex character likely found, or is not 32 hex characters.')
        else:
            with open(self.rp('cetk'), 'rb') as tik:
                # read encrypted titlekey and common key index
                tik.seek(0x1BF)
                enc_titlekey = tik.read(0x10)
                tik.seek(0x1F1)
                common_key_index = ord(tik.read(1))

            # decrypt titlekey
            normalkey = keygen(key_x, int(common_key_y[common_key_index][dev], 16))
            cipher_titlekey = AES.new(normalkey, AES.MODE_CBC, title_id + (b'\0' * 8))
            self.titlekey = cipher_titlekey.decrypt(enc_titlekey)

        # create virtual files
        self.files = {}
        self.files['/ticket.bin'] = {'size': 0x350, 'offset': 0, 'type': 'raw', 'realfilepath': self.rp('cetk')}
        self.files['/tmd.bin'] = {'size': 0xB04 + (tmd_chunks_size), 'offset': 0, 'type': 'raw', 'realfilepath': self.rp('tmd')}
        self.files['/tmdchunks.bin'] = {'size': tmd_chunks_size, 'offset': 0xB04, 'type': 'raw', 'realfilepath': self.rp('tmd')}

        # read contents to generate virtual files
        self.cdn_content_size = 0
        for chunk in [tmd_chunks_raw[i:i + 30] for i in range(0, tmd_chunks_size, 0x30)]:
            content_id = chunk[0:4]
            content_index = chunk[4:6]
            if os.path.isfile(self.rp(content_id.hex())):
                realfilename = content_id.hex()
            elif os.path.isfile(self.rp(content_id.hex().upper())):
                realfilename = content_id.hex().upper()
            else:
                print('Content {}:{} not found, will not be included.'.format(content_id.hex(), content_index.hex()))
                continue
            content_size = int.from_bytes(chunk[8:16], 'big')
            filesize = os.path.getsize(self.rp(realfilename))
            if content_size != filesize:
                print('Warning: TMD Content size and filesize of {} are different.'.format(content_id.hex()))
            self.cdn_content_size += content_size
            content_is_encrypted = int.from_bytes(chunk[6:8], 'big') & 1
            filename = '/{}.{}.app'.format(content_index.hex(), content_id.hex())
            self.files[filename] = {'size': content_size, 'offset': 0, 'index': content_index, 'type': 'enc' if content_is_encrypted else 'raw', 'realfilepath': self.rp(realfilename)}

    def access(self, path, mode):
        pass

    # unused
    def chmod(self, *args, **kwargs):
        return None

    # unused
    def chown(self, *args, **kwargs):
        return None

    def create(self, *args, **kwargs):
        self.fd += 1
        return self.fd

    def flush(self, path, fh):
        return None

    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        if path == '/':
            st = {'st_mode': (stat.S_IFDIR | 0o555), 'st_nlink': 2}
        elif path.lower() in self.files:
            st = {'st_mode': (stat.S_IFREG | 0o444), 'st_size': self.files[path.lower()]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(errno.ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    # unused
    def mkdir(self, *args, **kwargs):
        return None

    # unused
    def mknod(self, *args, **kwargs):
        return None

    def open(self, path, flags):
        # TODO: maybe this should actually open the file. this isn't so easy
        #   because filenames are being changed in the mount. so right now,
        #   files are opened each time read is called.
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        return ['.', '..'] + [x[1:] for x in self.files]

    def read(self, path, size, offset, fh):
        fi = self.files[path.lower()]
        real_offset = fi['offset'] + offset
        with open(fi['realfilepath'], 'rb') as f:
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
                data = f.read(size)
                # set up a cipher
                cipher = AES.new(self.titlekey, AES.MODE_CBC, iv)
                # decrypt and slice to the exact size and position requested
                data = cipher.decrypt(data)[before:len(data) - after]

            return data

    # unused
    def readlink(self, *args, **kwargs):
        return None

    # unused
    def release(self, *args, **kwargs):
        return None

    # unused
    def releasedir(self, *args, **kwargs):
        return None

    # unused
    def rename(self, *args, **kwargs):
        return None

    # unused
    def rmdir(self, *args, **kwargs):
        return None

    def statfs(self, path):
        return {'f_bsize': 4096, 'f_blocks': self.cdn_content_size // 4096, 'f_bavail': 0, 'f_bfree': 0, 'f_files': len(self.files)}

    # unused
    def symlink(self, target, source):
        pass

    # unused
    # if this is set to None, some programs may crash.
    def truncate(self, path, length, fh=None):
        raise FuseOSError(errno.EPERM)

    # unused
    def utimens(self, *args, **kwargs):
        return None

    # unused
    def unlink(self, path):
        return None

    def write(self, path, data, offset, fh):
        raise FuseOSError(errno.EPERM)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS CDN contents.')
    parser.add_argument('--dec-key', help='decrypted titlekey')
    parser.add_argument('--dev', help='use dev keys', action='store_const', const=1, default=0)
    parser.add_argument('--fg', '-f', help='run in foreground', action='store_true')
    parser.add_argument('--do', help='debug output (python logging module)', action='store_true')
    parser.add_argument('-o', metavar='OPTIONS', help='mount options')
    parser.add_argument('cdn_dir', help='directory with CDN contents')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()
    try:
        opts = {o: True for o in a.o.split(',')}
    except AttributeError:
        opts = {}

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    fuse = FUSE(CDNContents(cdn_dir=a.cdn_dir, dev=a.dev, dec_key=a.dec_key), a.mount_point, foreground=a.fg or a.do, fsname=os.path.realpath(a.cdn_dir), ro=True, **opts)
