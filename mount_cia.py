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


# based on http://stackoverflow.com/questions/1766535/bit-hack-round-off-to-multiple-of-8/1766566#1766566
def new_offset(x):
    return (((x + 63) >> 6) << 6)  # - x


# these would have to be obtained from Process9 and that's annoying.
common_key_y = (
    ('D07B337F9CA4385932A2E25723232EB9', '85215E96CB95A9ECA4B4DE601CB562C7'),
    ('0C767230F0998F1C46828202FAACBE4C', '0C767230F0998F1C46828202FAACBE4C'),
    ('C475CB3AB8C788BB575E12A10907B8A4', 'C475CB3AB8C788BB575E12A10907B8A4'),
    ('E486EEE3D0C09C902F6686D4C06F649F', 'E486EEE3D0C09C902F6686D4C06F649F'),
    ('ED31BA9C04B067506C4497A35B7804FC', 'ED31BA9C04B067506C4497A35B7804FC'),
    ('5E66998AB4E8931606850FD7A16DD755', '5E66998AB4E8931606850FD7A16DD755')
)


class CTRImportableArchive(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, cia, dev):
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
        cia_stat = os.stat(cia)
        self.g_stat = {}
        self.g_stat['st_ctime'] = int(cia_stat.st_ctime)
        self.g_stat['st_mtime'] = int(cia_stat.st_mtime)
        self.g_stat['st_atime'] = int(cia_stat.st_atime)

        # open cia and get section sizes
        self.f = open(cia, 'rb')
        # TODO: do this based off the section sizes instead of file size.
        self.cia_size = os.path.getsize(cia)
        archive_header_size, cia_type, cia_version, cert_chain_size, ticket_size, tmd_size, meta_size, content_size = struct.unpack('<IHHIIIIQ', self.f.read(0x20))

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
        normalkey = keygen(key_x, int(common_key_y[common_key_index][dev], 16))
        cipher_titlekey = AES.new(normalkey, AES.MODE_CBC, title_id + (b'\0' * 8))
        self.titlekey = cipher_titlekey.decrypt(enc_titlekey)

        # get content count
        self.f.seek(tmd_offset + 0x1DE)
        content_count = int.from_bytes(self.f.read(2), 'big')

        # get offset for tmd chunks, mostly so it can be put into a tmdchunks.bin virtual file
        tmd_chunks_offset = tmd_offset + 0xB04
        tmd_chunks_size = content_count * 0x30

        # create virtual files
        self.files = {}
        self.files['/header.bin'] = {'size': archive_header_size, 'offset': 0, 'type': 'raw'}
        self.files['/cert.bin'] = {'size': cert_chain_size, 'offset': cert_chain_offset, 'type': 'raw'}
        self.files['/ticket.bin'] = {'size': ticket_size, 'offset': ticket_offset, 'type': 'raw'}
        self.files['/tmd.bin'] = {'size': tmd_size, 'offset': tmd_offset, 'type': 'raw'}
        self.files['/tmdchunks.bin'] = {'size': tmd_chunks_size, 'offset': tmd_chunks_offset, 'type': 'raw'}
        if meta_size:
            self.files['/meta.bin'] = {'size': meta_size, 'offset': meta_offset, 'type': 'raw'}
            # show icon.bin if meta size is the expected size
            # in practice this never changes, but better to be safe
            if meta_size == 0x3AC0:
                self.files['/icon.bin'] = {'size': 0x36C0, 'offset': meta_offset + 0x400, 'type': 'raw'}

        self.f.seek(tmd_chunks_offset)
        tmd_chunks_raw = self.f.read(tmd_chunks_size)

        # read chunks to generate virtual files
        current_offset = content_offset
        for chunk in [tmd_chunks_raw[i:i + 30] for i in range(0, content_count * 0x30, 0x30)]:
            content_id = chunk[0:4]
            content_index = chunk[4:6]
            content_size = int.from_bytes(chunk[8:16], 'big')
            content_is_encrypted = int.from_bytes(chunk[6:8], 'big') & 1
            filename = '/{}.{}.app'.format(content_index.hex(), content_id.hex())
            self.files[filename] = {'size': content_size, 'offset': current_offset, 'index': content_index, 'type': 'enc' if content_is_encrypted else 'raw'}
            current_offset += new_offset(content_size)

    def __del__(self):
        try:
            self.f.close()
        except AttributeError:
            pass

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
        return self.f.flush()

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
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        return ['.', '..'] + [x[1:] for x in self.files]

    def read(self, path, size, offset, fh):
        fi = self.files[path.lower()]
        real_offset = fi['offset'] + offset
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
            data = self.f.read(size)
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
        return {'f_bsize': 4096, 'f_blocks': self.cia_size // 4096, 'f_bavail': 0, 'f_bfree': 0, 'f_files': len(self.files)}

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
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS CTR Importable Archive files.')
    parser.add_argument('--dev', help='use dev keys', action='store_const', const=1, default=0)
    parser.add_argument('--fg', '-f', help='run in foreground', action='store_true')
    parser.add_argument('--do', help='debug output (python logging module)', action='store_true')
    parser.add_argument('-o', metavar='OPTIONS', help='mount options')
    parser.add_argument('cia', help='CIA file')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()
    try:
        opts = {o: True for o in a.o.split(',')}
    except AttributeError:
        opts = {}

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    fuse = FUSE(CTRImportableArchive(cia=a.cia, dev=a.dev), a.mount_point, foreground=a.fg or a.do, fsname=os.path.realpath(a.cia), ro=True, **opts)
