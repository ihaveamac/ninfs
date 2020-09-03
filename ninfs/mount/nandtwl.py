# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts Nintendo DSi NAND images, creating a virtual filesystem of decrypted partitions.
"""

import logging
import os
from errno import ENOENT, EROFS
from hashlib import sha1
from stat import S_IFDIR, S_IFREG
from struct import pack
from sys import exit, argv
from typing import BinaryIO

from pyctr.crypto import CryptoEngine, Keyslot
from pyctr.util import readbe, readle

from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context, get_time, realpath


class TWLNandImageMount(LoggingMixIn, Operations):
    fd = 0

    def __init__(self, nand_fp: BinaryIO, g_stat: dict, consoleid: str = None, cid: str = None,
                 readonly: bool = False):
        self.crypto = CryptoEngine(setup_b9_keys=False)
        self.readonly = readonly

        self.g_stat = g_stat

        self.files = {}

        self.f = nand_fp

        nand_size = nand_fp.seek(0, 2)
        if nand_size < 0xF000000:
            exit(f'NAND is too small (expected >= 0xF000000, got {nand_size:#X}')
        if nand_size & 0x40 == 0x40:
            self.files['/nocash_blk.bin'] = {'offset': nand_size - 0x40, 'size': 0x40, 'type': 'dec'}

        nand_fp.seek(0)

        try:
            consoleid = bytes.fromhex(consoleid)
        except (ValueError, TypeError):
            try:
                with open(consoleid, 'rb') as f:
                    consoleid = f.read(0x10)
            except (FileNotFoundError, TypeError):
                # read Console ID and CID from footer
                try:
                    nocash_blk: bytes = self.read('/nocash_blk.bin', 0x40, 0, 0)
                except KeyError:
                    if consoleid is None:
                        exit('Nocash block not found, and Console ID not provided.')
                    else:
                        exit('Failed to convert Console ID to bytes, or file did not exist.')
                else:
                    if len(nocash_blk) != 0x40:
                        exit('Failed to read 0x40 of footer (this should never happen)')
                    if nocash_blk[0:0x10] != b'DSi eMMC CID/CPU':
                        exit('Failed to find footer magic "DSi eMMC CID/CPU"')
                    if len(set(nocash_blk[0x10:0x40])) == 1:
                        exit('Nocash block is entirely empty. Maybe re-dump NAND with another exploit, or manually '
                             'get Console ID with some other method.')
                    cid = nocash_blk[0x10:0x20]
                    consoleid = nocash_blk[0x20:0x28][::-1]
                    print('Console ID and CID read from nocash block.')

        twl_consoleid_list = (readbe(consoleid[4:8]), readbe(consoleid[0:4]))

        key_x_list = [twl_consoleid_list[0],
                      twl_consoleid_list[0] ^ 0x24EE6906,
                      twl_consoleid_list[1] ^ 0xE65B601D,
                      twl_consoleid_list[1]]

        self.crypto.set_keyslot('x', Keyslot.TWLNAND, pack('<4I', *key_x_list))

        nand_fp.seek(0)
        header_enc = nand_fp.read(0x200)

        if cid:
            if not isinstance(cid, bytes):  # if cid was already read above
                try:
                    cid = bytes.fromhex(cid)
                except ValueError:
                    try:
                        with open(cid, 'rb') as f:
                            cid = f.read(0x10)
                    except FileNotFoundError:
                        exit('Failed to convert CID to bytes, or file did not exist.')
            self.ctr = readle(sha1(cid).digest()[0:16])

        else:
            # attempt to generate counter
            block_0x1c = readbe(header_enc[0x1C0:0x1D0])
            blk_xored = block_0x1c ^ 0x1804060FE03B77080000896F06000002
            ctr_offs = self.crypto.create_ecb_cipher(Keyslot.TWLNAND).decrypt(blk_xored.to_bytes(0x10, 'little'))
            self.ctr = int.from_bytes(ctr_offs, 'big') - 0x1C

            # try the counter
            block_0x1d = header_enc[0x1D0:0x1E0]
            out = self.crypto.create_ctr_cipher(Keyslot.TWLNAND, self.ctr + 0x1D).decrypt(block_0x1d)
            if out != b'\xce<\x06\x0f\xe0\xbeMx\x06\x00\xb3\x05\x01\x00\x00\x02':
                exit('Counter could not be automatically generated. Please provide the CID, '
                     'or ensure the provided Console ID is correct.')
            print('Counter automatically generated.')

        self.files['/stage2_infoblk1.bin'] = {'offset': 0x200, 'size': 0x200, 'type': 'dec'}
        self.files['/stage2_infoblk2.bin'] = {'offset': 0x400, 'size': 0x200, 'type': 'dec'}
        self.files['/stage2_infoblk3.bin'] = {'offset': 0x600, 'size': 0x200, 'type': 'dec'}
        self.files['/stage2_bootldr.bin'] = {'offset': 0x800, 'size': 0x4DC00, 'type': 'dec'}
        self.files['/stage2_footer.bin'] = {'offset': 0x4E400, 'size': 0x400, 'type': 'dec'}
        self.files['/diag_area.bin'] = {'offset': 0xFFA00, 'size': 0x400, 'type': 'dec'}

        header = self.crypto.create_ctr_cipher(Keyslot.TWLNAND, self.ctr).decrypt(header_enc)
        mbr = header[0x1BE:0x200]
        mbr_sig = mbr[0x40:0x42]
        if mbr_sig != b'\x55\xaa':
            exit(f'MBR signature not found (expected "55aa", got "{mbr_sig.hex()}"). '
                 f'Make sure the provided Console ID and CID are correct.')

    def __del__(self, *args):
        try:
            self.f.close()
        except AttributeError:
            pass

    destroy = __del__

    def flush(self, path, fh):
        return self.f.flush()

    @_c.ensure_lower_path
    def getattr(self, path, fh=None):
        uid, gid, pid = fuse_get_context()
        if path == '/':
            st = {'st_mode': (S_IFDIR | (0o555 if self.readonly else 0o777)), 'st_nlink': 2}
        elif path in self.files:
            st = {'st_mode': (S_IFREG | (0o444 if self.readonly else 0o666)),
                  'st_size': self.files[path]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(ENOENT)
        return {**st, **self.g_stat, 'st_uid': uid, 'st_gid': gid}

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    @_c.ensure_lower_path
    def readdir(self, path, fh):
        yield from ('.', '..')
        yield from (x[1:] for x in self.files)

    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        fi = self.files[path]
        real_offset = fi['offset'] + offset
        if fi['offset'] + offset > fi['offset'] + fi['size']:
            return b''
        if offset + size > fi['size']:
            size = fi['size'] - offset

        self.f.seek(real_offset)
        data = self.f.read(size)
        if fi['type'] == 'enc':
            before = offset % 16
            after = (offset + size) % 16
            data = (b'\0' * before) + data + (b'\0' * after)
            iv = self.ctr + (real_offset >> 4)
            data = self.crypto.create_ctr_cipher(Keyslot.TWLNAND, iv).decrypt(data)[before:len(data) - after]

        return data

    @_c.ensure_lower_path
    def statfs(self, path):
        return {'f_bsize': 4096, 'f_blocks': 0xF000000 // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}

    @_c.ensure_lower_path
    def write(self, path, data, offset, fh):
        if self.readonly:
            raise FuseOSError(EROFS)

        fi = self.files[path]
        real_offset = fi['offset'] + offset
        real_len = len(data)
        if offset >= fi['size']:
            print('attempt to start writing past file')
            return real_len
        if real_offset + len(data) > fi['offset'] + fi['size']:
            data = data[:-((real_offset + len(data)) - fi['size'])]

        if fi['type'] == 'dec':
            self.f.seek(real_offset)
            self.f.write(data)

        else:
            before = offset % 16
            after = 16 - ((offset + real_len) % 16)
            if after == 16:
                after = 0
            iv = self.ctr + (real_offset >> 4)
            data = (b'\0' * before) + data + (b'\0' * after)
            out_data = self.crypto.create_ctr_cipher(Keyslot.TWLNAND, iv).encrypt(data)[before:real_len - after]
            self.f.seek(real_offset)
            self.f.write(out_data)

        return real_len


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo DSi NAND images.',
                            parents=(_c.default_argp, _c.readonly_argp, _c.main_args('nand', 'DSi NAND image')))
    parser.add_argument('--console-id', help='Console ID, as hex or file')
    parser.add_argument('--cid', help='EMMC CID, as hex or file. Not required in 99%% of cases.', default=None)

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    nand_stat = get_time(a.nand)

    with open(a.nand, f'r{"" if a.ro else "+"}b') as f:
        mount = TWLNandImageMount(nand_fp=f, g_stat=nand_stat, consoleid=a.console_id, cid=a.cid, readonly=a.ro)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'TWLFS'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            if _c.macos:
                path_to_show = realpath(a.nand).rsplit('/', maxsplit=2)
                opts['volname'] = f'Nintendo DSi NAND ({path_to_show[-2]}/{path_to_show[-1]})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = 'Nintendo DSi NAND'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=a.ro, nothreads=True, debug=a.d,
             fsname=realpath(a.nand).replace(',', '_'), **opts)
