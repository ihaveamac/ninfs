# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

"""
Mounts NAND images, creating a virtual filesystem of decrypted partitions. Can read essentials backup by GodMode9, else
OTP file/NAND CID must be provided in arguments.
"""

import logging
import os
from errno import EPERM, ENOENT, EROFS
from hashlib import sha1, sha256
from stat import S_IFDIR, S_IFREG
from sys import exit, argv
from traceback import print_exc
from typing import BinaryIO, AnyStr

from pyctr.crypto import CryptoEngine, Keyslot
from pyctr.types.exefs import ExeFSReader, InvalidExeFSError
from pyctr.util import readbe, readle, roundup
from . import _common as _c
# _common imports these from fusepy, and prints an error if it fails; this allows less duplicated code
from ._common import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
from .exefs import ExeFSMount

# ncsd image doesn't have the actual size
nand_size = {0x200000: 0x3AF00000, 0x280000: 0x4D800000}


class CTRNandImageMount(LoggingMixIn, Operations):
    fd = 0

    _essentials_mounted = False

    def __init__(self, nand_fp: BinaryIO, g_stat: os.stat_result, dev: bool = False, readonly: bool = False,
                 otp: bytes = None, cid: AnyStr = None):
        self.crypto = CryptoEngine(dev=dev)

        self.g_stat = {'st_ctime': int(g_stat.st_ctime), 'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        nand_fp.seek(0x100)  # screw the signature
        ncsd_header = nand_fp.read(0x100)
        if ncsd_header[0:4] != b'NCSD':
            exit('NCSD magic not found, is this a real Nintendo 3DS NAND image?')
        media_id = ncsd_header[0x8:0x10]
        if media_id != b'\0' * 8:
            exit('Media ID not all-zero, is this a real Nintendo 3DS NAND image?')

        # check for essential.exefs
        nand_fp.seek(0x200)
        try:
            exefs = ExeFSReader.load(nand_fp)
        except InvalidExeFSError:
            exefs = None

        otp_data = None
        if otp:
            try:
                with open(otp, 'rb') as f:
                    otp_data = f.read(0x200)
            except Exception:
                print(f'Failed to open and read given OTP ({otp}).\n')
                print_exc()
                exit(1)

        else:
            if exefs is None:
                exit('OTP not found, provide with --otp or embed essentials backup with GodMode9')
            else:
                if 'otp' in exefs.entries:
                    nand_fp.seek(exefs['otp'].offset + 0x400)
                    otp_data = nand_fp.read(exefs['otp'].size)
                else:
                    exit('"otp" not found in essentials backup, update with GodMode9 or provide with --otp')

        self.crypto.setup_keys_from_otp(otp_data)

        def generate_ctr():
            print('Attempting to generate Counter for CTR/TWL areas. If errors occur, provide the CID manually.')

            # -------------------------------------------------- #
            # attempt to generate CTR Counter
            nand_fp.seek(0xB9301D0)
            # these blocks are assumed to be entirely 00, so no need to xor anything
            ctrn_block_0x1d = nand_fp.read(0x10)
            ctrn_block_0x1e = nand_fp.read(0x10)
            for ks in (Keyslot.CTRNANDOld, Keyslot.CTRNANDNew):
                ctr_counter_offs = self.crypto.create_ecb_cipher(ks).decrypt(ctrn_block_0x1d)
                ctr_counter = int.from_bytes(ctr_counter_offs, 'big') - 0xB9301D

                # try the counter
                out = self.crypto.create_ctr_cipher(ks, ctr_counter + 0xB9301E).decrypt(ctrn_block_0x1e)
                if out == b'\0' * 16:
                    print('Counter for CTR area automatically generated.')
                    self.ctr = ctr_counter
                    break
            else:
                print('Counter could not be generated for CTR area. Related virtual files will not appear.')
                self.ctr = None

            # -------------------------------------------------- #
            # attempt to generate TWL Counter
            nand_fp.seek(0x1C0)
            twln_block_0x1c = readbe(nand_fp.read(0x10))
            twl_blk_xored = twln_block_0x1c ^ 0x18000601A03F97000000A97D04000004
            twl_counter_offs = self.crypto.create_ecb_cipher(0x03).decrypt(twl_blk_xored.to_bytes(0x10, 'little'))
            twl_counter = int.from_bytes(twl_counter_offs, 'big') - 0x1C

            # try the counter
            twln_block_0x1d = nand_fp.read(0x10)
            out = self.crypto.create_ctr_cipher(0x03, twl_counter + 0x1D).decrypt(twln_block_0x1d)
            if out == b'\x8e@\x06\x01\xa0\xc3\x8d\x80\x04\x00\xb3\x05\x01\x00\x00\x00':
                print('Counter for TWL area automatically generated.')
                self.ctr_twl = twl_counter
            else:
                print('Counter could not be generated for TWL area. Related virtual files will not appear.')
                self.ctr_twl = None

        cid_data = None
        if cid:
            try:
                with open(cid, 'rb') as f:
                    cid_data = f.read(0x200)
            except Exception:
                print(f'Failed to open and read given CID ({cid}).')
                print('If you want to attempt Counter generation, do not provide a CID path.\n')
                print_exc()
                exit(1)

        else:
            if exefs is None:
                generate_ctr()
            else:
                if 'nand_cid' in exefs.entries:
                    nand_fp.seek(exefs['nand_cid'].offset + 0x400)
                    cid_data = nand_fp.read(exefs['nand_cid'].size)
                else:
                    print('"nand_cid" not found in essentials backup, update with GodMode9 or provide with --cid')
                    generate_ctr()

        if cid_data:
            self.ctr = readbe(sha256(cid_data).digest()[0:16])
            self.ctr_twl = readle(sha1(cid_data).digest()[0:16])

        if not (self.ctr or self.ctr_twl):
            exit("Couldn't generate Counter for both CTR/TWL. "
                 "Make sure the OTP is correct, or provide the CID manually.")

        nand_fp.seek(0, 2)
        raw_nand_size = nand_fp.tell()

        self.real_nand_size = nand_size[readle(ncsd_header[4:8])]

        self.files = {'/nand_hdr.bin': {'size': 0x200, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'},
                      '/nand.bin': {'size': raw_nand_size, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'},
                      '/nand_minsize.bin': {'size': self.real_nand_size, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'}}

        nand_fp.seek(0x12C00)
        keysect_enc = nand_fp.read(0x200)
        if len(set(keysect_enc)) != 1:
            keysect_dec = self.crypto.create_ecb_cipher(0x11).decrypt(keysect_enc)
            # i'm cheating here by putting the decrypted version in memory and
            #   not reading from the image every time. but it's not AES-CTR so
            #   fuck that.
            self.files['/sector0x96.bin'] = {'size': 0x200, 'offset': 0x12C00, 'keyslot': 0x11, 'type': 'keysect',
                                             'content': keysect_dec}

        ncsd_part_fstype = ncsd_header[0x10:0x18]
        ncsd_part_crypttype = ncsd_header[0x18:0x20]
        ncsd_part_raw = ncsd_header[0x20:0x60]
        ncsd_partitions = [[readle(ncsd_part_raw[i:i + 4]) * 0x200,
                            readle(ncsd_part_raw[i + 4:i + 8]) * 0x200] for i in range(0, 0x40, 0x8)]

        # including padding for crypto
        if self.ctr_twl:
            twl_mbr = self.crypto.create_ctr_cipher(Keyslot.TWLNAND,
                                                    self.ctr_twl + 0x1B).decrypt(ncsd_header[0xB0:0x100])[0xE:0x50]
            if twl_mbr[0x40:0x42] == b'\x55\xaa':
                twl_partitions = [[readle(twl_mbr[i + 8:i + 12]) * 0x200,
                                   readle(twl_mbr[i + 12:i + 16]) * 0x200] for i in range(0, 0x40, 0x10)]
            else:
                twl_partitions = None

            self.files['/twlmbr.bin'] = {'size': 0x42, 'offset': 0x1BE, 'keyslot': Keyslot.TWLNAND, 'type': 'twlmbr',
                                         'content': twl_mbr}
        else:
            twl_partitions = None

        # then actually parse the partitions to create files
        firm_idx = 0
        for idx, part in enumerate(ncsd_partitions):
            if ncsd_part_fstype[idx] == 0:
                continue
            print(f'ncsd idx:{idx} fstype:{ncsd_part_fstype[idx]} crypttype:{ncsd_part_crypttype[idx]} '
                  f'offset:{part[0]:08x} size:{part[1]:08x} ', end='')
            if idx == 0:
                if self.ctr_twl:
                    self.files['/twl_full.img'] = {'size': part[1], 'offset': part[0], 'keyslot': Keyslot.TWLNAND,
                                                   'type': 'enc'}
                    print('/twl_full.img')
                    if twl_partitions:
                        twl_part_fstype = 0
                        for t_idx, t_part in enumerate(twl_partitions):
                            if t_part[0] != 0:
                                print(f'twl  idx:{t_idx}                      '
                                      f'offset:{t_part[0]:08x} size:{t_part[1]:08x} ', end='')
                                if twl_part_fstype == 0:
                                    self.files['/twln.img'] = {'size': t_part[1], 'offset': t_part[0],
                                                               'keyslot': Keyslot.TWLNAND, 'type': 'enc'}
                                    print('/twln.img')
                                    twl_part_fstype += 1
                                elif twl_part_fstype == 1:
                                    self.files['/twlp.img'] = {'size': t_part[1], 'offset': t_part[0],
                                                               'keyslot': Keyslot.TWLNAND, 'type': 'enc'}
                                    print('/twlp.img')
                                    twl_part_fstype += 1
                                else:
                                    self.files[f'/twl_unk{twl_part_fstype}.img'] = {'size': t_part[1],
                                                                                    'offset': t_part[0],
                                                                                    'keyslot': Keyslot.TWLNAND,
                                                                                    'type': 'enc'}
                                    print(f'/twl_unk{twl_part_fstype}.img')
                                    twl_part_fstype += 1
                else:
                    print('<ctr_twl not set>')

            elif self.ctr:
                if ncsd_part_fstype[idx] == 3:
                    # boot9 hardcoded this keyslot, i'll do this properly later
                    self.files[f'/firm{firm_idx}.bin'] = {'size': part[1], 'offset': part[0], 'keyslot': Keyslot.FIRM,
                                                          'type': 'enc'}
                    print(f'/firm{firm_idx}.bin')
                    firm_idx += 1

                elif ncsd_part_fstype[idx] == 1 and ncsd_part_crypttype[idx] >= 2:
                    ctrnand_keyslot = Keyslot.CTRNANDOld if ncsd_part_crypttype[idx] == 2 else Keyslot.CTRNANDNew
                    self.files['/ctrnand_full.img'] = {'size': part[1], 'offset': part[0], 'keyslot': ctrnand_keyslot,
                                                       'type': 'enc'}
                    print('/ctrnand_full.img')
                    nand_fp.seek(part[0])
                    iv = self.ctr + (part[0] >> 4)
                    ctr_mbr = self.crypto.create_ctr_cipher(ctrnand_keyslot, iv).decrypt(
                        nand_fp.read(0x200))[0x1BE:0x200]
                    if ctr_mbr[0x40:0x42] == b'\x55\xaa':
                        ctr_partitions = [[readle(ctr_mbr[i + 8:i + 12]) * 0x200,
                                           readle(ctr_mbr[i + 12:i + 16]) * 0x200]
                                          for i in range(0, 0x40, 0x10)]
                        ctr_part_fstype = 0
                        for c_idx, c_part in enumerate(ctr_partitions):
                            if c_part[0] != 0:
                                print(f'ctr  idx:{c_idx}                      offset:{part[0] + c_part[0]:08x} '
                                      f'size:{c_part[1]:08x} ', end='')
                                if ctr_part_fstype == 0:
                                    self.files['/ctrnand_fat.img'] = {'size': c_part[1], 'offset': part[0] + c_part[0],
                                                                      'keyslot': ctrnand_keyslot, 'type': 'enc'}
                                    print('/ctrnand_fat.img')
                                    ctr_part_fstype += 1
                                else:
                                    self.files[f'/ctr_unk{ctr_part_fstype}.img'] = {'size': c_part[1],
                                                                                    'offset': part[0] + c_part[0],
                                                                                    'keyslot': ctrnand_keyslot,
                                                                                    'type': 'enc'}
                                    print(f'/ctr_unk{ctr_part_fstype}.img')
                                    ctr_part_fstype += 1

                elif ncsd_part_fstype[idx] == 4:
                    self.files['/agbsave.bin'] = {'size': part[1], 'offset': part[0], 'keyslot': Keyslot.AGB,
                                                  'type': 'enc'}
                    print('/agbsave.bin')

            else:
                print('<ctr not set>')

        self.readonly = readonly

        # GM9 bonus drive
        if raw_nand_size != self.real_nand_size:
            nand_fp.seek(self.real_nand_size)
            bonus_drive_header = nand_fp.read(0x200)
            if bonus_drive_header[0x1FE:0x200] == b'\x55\xAA':
                self.files['/bonus.img'] = {'size': raw_nand_size - self.real_nand_size, 'offset': self.real_nand_size,
                                            'keyslot': 0xFF, 'type': 'raw'}

        self.f = nand_fp

        if exefs is not None:
            exefs_size = sum(roundup(x.size, 0x200) for x in exefs.entries.values()) + 0x200
            self.files['/essential.exefs'] = {'size': exefs_size, 'offset': 0x200, 'keyslot': 0xFF, 'type': 'raw'}
            try:
                exefs_vfp = _c.VirtualFileWrapper(self, '/essential.exefs', exefs_size)
                self.exefs_fuse = ExeFSMount(exefs_vfp, g_stat=g_stat)
                self.exefs_fuse.init('/')
                self._essentials_mounted = True
            except Exception as e:
                print(f'Failed to mount essential.exefs: {type(e).__name__}: {e}')

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
        if path.startswith('/essential/'):
            return self.exefs_fuse.getattr(_c.remove_first_dir(path), fh)
        else:
            uid, gid, pid = fuse_get_context()
            if path in {'/', '/essential'}:
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
        if path.startswith('/essential'):
            yield from self.exefs_fuse.readdir(_c.remove_first_dir(path), fh)
        elif path == '/':
            yield from ('.', '..')
            yield from (x[1:] for x in self.files)
            if self._essentials_mounted:
                yield 'essential'

    @_c.ensure_lower_path
    def read(self, path, size, offset, fh):
        if path.startswith('/essential/'):
            return self.exefs_fuse.read(_c.remove_first_dir(path), size, offset, fh)
        fi = self.files[path]
        real_offset = fi['offset'] + offset
        if fi['offset'] + offset > fi['offset'] + fi['size']:
            return b''
        if offset + size > fi['size']:
            size = fi['size'] - offset

        if fi['type'] == 'raw':
            self.f.seek(real_offset)
            data = self.f.read(size)

        elif fi['type'] == 'enc':
            self.f.seek(real_offset)
            data = self.f.read(size)
            # thanks Stary2001
            before = offset % 16
            after = (offset + size) % 16
            data = (b'\0' * before) + data + (b'\0' * after)
            iv = (self.ctr if fi['keyslot'] > Keyslot.TWLNAND else self.ctr_twl) + (real_offset >> 4)
            data = self.crypto.create_ctr_cipher(fi['keyslot'], iv).decrypt(data)[before:len(data) - after]

        elif fi['type'] in {'keysect', 'twlmbr', 'info'}:
            # being lazy here since twlmbr starts at a weird offset. i'll do
            #   it properly some day. maybe.
            data = fi['content'][offset:offset + size]

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
        if path.startswith('/essential/'):
            return self.exefs_fuse.statfs(_c.remove_first_dir(path))
        return {'f_bsize': 4096, 'f_blocks': self.real_nand_size // 4096, 'f_bavail': 0, 'f_bfree': 0,
                'f_files': len(self.files)}

    @_c.ensure_lower_path
    def write(self, path, data, offset, fh):
        if self.readonly:
            raise FuseOSError(EROFS)
        if path.startswith('/essential/'):
            raise FuseOSError(EPERM)
        fi = self.files[path]
        if fi['type'] == 'info':
            raise FuseOSError(EPERM)
        real_offset = fi['offset'] + offset
        real_len = len(data)
        if offset >= fi['size']:
            print('attempt to start writing past file')
            return real_len
        if real_offset + len(data) > fi['offset'] + fi['size']:
            data = data[:-((real_offset + len(data)) - fi['size'])]

        if fi['type'] == 'raw':
            self.f.seek(real_offset)
            self.f.write(data)

        elif fi['type'] == 'enc':
            twl = fi['keyslot'] < Keyslot.CTRNANDOld
            before = offset % 16
            if twl:
                after = 16 - ((offset + real_len) % 16)
                if after == 16:
                    after = 0
            else:
                after = 0  # not needed for ctr
            iv = (self.ctr_twl if twl else self.ctr) + (real_offset >> 4)
            out_data = self.crypto.create_ctr_cipher(fi['keyslot'], iv).encrypt(
                (b'\0' * before) + data + (b'\0' * after))
            self.f.seek(real_offset)
            self.f.write(out_data[before:])

        elif fi['type'] == 'twlmbr':
            twlmbr = bytearray(fi['content'])
            twlmbr[offset:offset + len(data)] = data
            final = bytes(twlmbr)
            self.f.seek(fi['offset'])
            self.f.write(self.crypto.create_ctr_cipher(fi['keyslot'], self.ctr_twl + 0x1B).encrypt(
                (b'\0' * 0xE) + final)[0xE:0x50])
            # noinspection PyTypeChecker
            fi['content'] = final

        elif fi['type'] == 'keysect':
            keysect = bytearray(fi['content'])
            keysect[offset:offset + len(data)] = data
            final = bytes(keysect)
            cipher_keysect = self.crypto.create_ecb_cipher(0x11)
            self.f.seek(fi['offset'])
            self.f.write(cipher_keysect.encrypt(final))
            # noinspection PyTypeChecker
            fi['content'] = final

        return real_len


def main(prog: str = None, args: list = None):
    from argparse import ArgumentParser
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS NAND images.',
                            parents=(_c.default_argp, _c.readonly_argp, _c.dev_argp,
                                     _c.main_args('nand', 'NAND image')))
    parser.add_argument('--otp', help='path to otp (enc/dec); not needed if NAND image has essentials backup from '
                                      'GodMode9')
    parser.add_argument('--cid', help='NAND CID; not needed if NAND image has essentials backup from GodMode9')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG, filename=a.do)

    nand_stat = os.stat(a.nand)

    with open(a.nand, f'r{"" if a.ro else "+"}b') as f:
        # noinspection PyTypeChecker
        mount = CTRNandImageMount(nand_fp=f, dev=a.dev, g_stat=nand_stat, readonly=a.ro, otp=a.otp, cid=a.cid)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'CTRFS'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            if _c.macos:
                path_to_show = os.path.realpath(a.nand).rsplit('/', maxsplit=2)
                opts['volname'] = f'Nintendo 3DS NAND ({path_to_show[-2]}/{path_to_show[-1]})'
            elif _c.windows:
                # volume label can only be up to 32 chars
                opts['volname'] = 'Nintendo 3DS NAND'
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=a.ro, nothreads=True, debug=a.d,
             fsname=os.path.realpath(a.nand).replace(',', '_'), **opts)
