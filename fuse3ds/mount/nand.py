#!/usr/bin/env python3

"""
Mounts NAND images, creating a virtual filesystem of decrypted partitions. Can read essentials backup by GodMode9, else OTP file/NAND CID must be provided in arguments.
"""

import logging
import os
from argparse import ArgumentParser
from errno import EPERM, ENOENT, EROFS
from hashlib import sha1, sha256
from stat import S_IFDIR, S_IFREG
from struct import unpack, pack
from sys import exit, argv
from typing import BinaryIO, AnyStr

from pyctr.crypto import CTRCrypto
from pyctr.exefs import ExeFSReader, InvalidExeFSError
from pyctr.util import readbe, readle, roundup

from . import _common as _c
from .exefs import ExeFSMount

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn, fuse_get_context
except ModuleNotFoundError:
    exit("fuse module not found, please install fusepy to mount images "
         "(`{} -mpip install https://github.com/billziss-gh/fusepy/archive/windows.zip`).".format(_c.python_cmd))
except Exception as e:
    exit("Failed to import the fuse module:\n"
         "{}: {}".format(type(e).__name__, e))

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ModuleNotFoundError:
    exit("Cryptodome module not found, please install pycryptodomex for encryption support "
         "(`{} install pycryptodomex`).".format(_c.python_cmd))
except Exception as e:
    exit("Failed to import the Cryptodome module:\n"
         "{}: {}".format(type(e).__name__, e))

# ncsd image doesn't have the actual size
nand_size = {0x200000: 0x3AF00000, 0x280000: 0x4D800000}


class NANDImageMount(LoggingMixIn, Operations):
    fd = 0

    _essentials_mounted = False

    def __init__(self, nand_fp: BinaryIO, g_stat: os.stat_result, dev: bool = False, readonly: bool = False,
                 otp: bytes = None, cid: AnyStr = None):
        self.crypto = CTRCrypto(is_dev=dev)

        try:
            self.crypto.setup_keys_from_boot9()
        except crypto.BootromNotFoundError as e:
            print("Bootrom was not found.")

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
        if otp or cid:
            if otp:
                with open(otp, 'rb') as f:
                    otp = f.read(0x200)
            else:
                exit('OTP not found, provide otp-file with --otp (or embed essentials backup with GodMode9)')
            if cid:
                try:
                    cid = bytes.fromhex(cid)
                except ValueError:
                    try:
                        with open(cid, 'rb') as f:
                            cid = f.read(0x10)
                    except FileNotFoundError:
                        exit('Failed to convert CID to bytes, or file did not exist.')
                if len(cid) != 0x10:
                    exit('CID is not 16 bytes.')
            else:
                exit('NAND CID not found, provide cid with --cid (or embed essentials backup with GodMode9)')
        else:
            if exefs is None:
                if not otp:
                    exit('OTP not found, provide otp-file with --otp (or embed essentials backup with GodMode9)')
                if not cid:
                    exit('NAND CID not found, provide cid with --cid (or embed essentials backup with GodMode9)')
            else:
                if 'otp' in exefs.entries:
                    nand_fp.seek(exefs['otp'].offset + 0x400)
                    otp = nand_fp.read(exefs['otp'].size)
                if 'nand_cid' in exefs.entries:
                    nand_fp.seek(exefs['nand_cid'].offset + 0x400)
                    cid = nand_fp.read(exefs['nand_cid'].size)
                if not (otp or cid):
                    exit('otp and nand_cid somehow not found in essentials backup. update with GodMode9 or '
                         'provide OTP/NAND CID with --otp/--cid.')

        self.ctr = readbe(sha256(cid).digest()[0:16])
        self.ctr_twl = readle(sha1(cid).digest()[0:16])

        cipher_otp = AES.new(self.crypto.otp_key, AES.MODE_CBC, self.crypto.otp_iv)
        if otp[0:4][::-1] == b'\xDE\xAD\xB0\x0F':
            otp_enc = cipher_otp.encrypt(otp)
            otp_keysect_hash = sha256(otp_enc[0:0x90]).digest()
        else:
            otp_keysect_hash = sha256(otp[0:0x90]).digest()
            otp = cipher_otp.decrypt(otp)

        # generate twl keys
        # TODO: put this in CTRCrypto
        twl_cid_lo, twl_cid_hi = readle(otp[0x08:0xC]), readle(otp[0xC:0x10])
        twl_cid_lo ^= 0xB358A6AF
        twl_cid_lo |= 0x80000000
        twl_cid_hi ^= 0x08C267B7
        twl_cid_lo = twl_cid_lo.to_bytes(4, 'little')
        twl_cid_hi = twl_cid_hi.to_bytes(4, 'little')

        twl_key_x = readle(twl_cid_lo + b'NINTENDO' + twl_cid_hi)
        self.crypto.set_keyslot('x', 0x03, twl_key_x)

        # only keys for slots 0x04-0x07 are used, and keyX for all of them are
        #   the same, so this only uses the data needed for this key
        # thanks Stary2001 (from 3ds_tools)
        tmp_otp_data = otp[0x90:0xAC] + self.crypto.b9_extdata_otp
        console_key_xy = sha256(tmp_otp_data).digest()
        console_key_x = readbe(console_key_xy[0:16])
        console_key_y = readbe(console_key_xy[16:32])
        console_normalkey = self.crypto.keygen_manual(console_key_x, console_key_y)

        cipher_keygen = AES.new(console_normalkey, AES.MODE_CBC, self.crypto.b9_extdata_keygen_iv)
        key_x = readbe(cipher_keygen.encrypt(self.crypto.b9_extdata_keygen))

        self.crypto.set_keyslot('x', 0x04, key_x)
        self.crypto.set_keyslot('x', 0x05, key_x)
        self.crypto.set_keyslot('x', 0x06, key_x)
        self.crypto.set_keyslot('x', 0x07, key_x)

        self.g_stat = {'st_ctime': int(g_stat.st_ctime), 'st_mtime': int(g_stat.st_mtime),
                       'st_atime': int(g_stat.st_atime)}

        nand_fp.seek(0, 2)
        raw_nand_size = nand_fp.tell()

        self.real_nand_size = nand_size[readle(ncsd_header[4:8])]

        self.files = {'/nand_hdr.bin': {'size': 0x200, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'},
                      '/nand.bin': {'size': raw_nand_size, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'},
                      '/nand_minsize.bin': {'size': self.real_nand_size, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'}}

        nand_fp.seek(0x12C00)
        keysect_enc = nand_fp.read(0x200)
        if keysect_enc != b'\0' * 0x200 and keysect_enc != b'\xFF' * 0x200:
            keysect_x = otp_keysect_hash[0:16]
            keysect_y = otp_keysect_hash[16:32]
            # TODO: put this in CTRCrypto
            self.keysect_key = self.crypto.keygen_manual(readbe(keysect_x), readbe(keysect_y))
            cipher_keysect = AES.new(self.keysect_key, AES.MODE_ECB)
            keysect_dec = cipher_keysect.decrypt(keysect_enc)
            # i'm cheating here by putting the decrypted version in memory and
            #   not reading from the image every time. but it's not AES-CTR so
            #   fuck that.
            self.files['/sector0x96.bin'] = {'size': 0x200, 'offset': 0x12C00, 'keyslot': 0xFF, 'type': 'keysect',
                                             'content': keysect_dec}

        ncsd_part_fstype = ncsd_header[0x10:0x18]
        ncsd_part_crypttype = ncsd_header[0x18:0x20]
        ncsd_part_raw = ncsd_header[0x20:0x60]
        ncsd_partitions = [[readle(ncsd_part_raw[i:i + 4]) * 0x200,
                            readle(ncsd_part_raw[i + 4:i + 8]) * 0x200] for i in range(0, 0x40, 0x8)]

        # including padding for crypto
        twl_mbr = self.crypto.aes_ctr(0x03, self.ctr_twl + 0x1B, ncsd_header[0xB0:0x100])[0xE:0x50]
        twl_partitions = [[readle(twl_mbr[i + 8:i + 12]) * 0x200,
                           readle(twl_mbr[i + 12:i + 16]) * 0x200] for i in range(0, 0x40, 0x10)]

        self.files['/twlmbr.bin'] = {'size': 0x42, 'offset': 0x1BE, 'keyslot': 0x03, 'type': 'twlmbr',
                                     'content': twl_mbr}

        # then actually parse the partitions to create files
        firm_idx = 0
        for idx, part in enumerate(ncsd_partitions):
            if ncsd_part_fstype[idx] == 0:
                continue
            print('ncsd idx:{0} fstype:{1} crypttype:{2} offset:{3[0]:08x} size:{3[1]:08x} '
                  .format(idx, ncsd_part_fstype[idx], ncsd_part_crypttype[idx], part), end='')
            if idx == 0:
                self.files['/twl_full.img'] = {'size': part[1], 'offset': part[0], 'keyslot': 0x03, 'type': 'enc'}
                print('/twl_full.img')
                twl_part_fstype = 0
                for t_idx, t_part in enumerate(twl_partitions):
                    if t_part[0] != 0:
                        print('twl  idx:{0}                      offset:{1[0]:08x} size:{1[1]:08x} '
                              .format(t_idx, t_part), end='')
                        if twl_part_fstype == 0:
                            self.files['/twln.img'] = {'size': t_part[1], 'offset': t_part[0], 'keyslot': 0x03,
                                                       'type': 'enc'}
                            print('/twln.img')
                            twl_part_fstype += 1
                        elif twl_part_fstype == 1:
                            self.files['/twlp.img'] = {'size': t_part[1], 'offset': t_part[0], 'keyslot': 0x03,
                                                       'type': 'enc'}
                            print('/twlp.img')
                            twl_part_fstype += 1
                        else:
                            self.files['/twl_unk{}.img'.format(twl_part_fstype)] = {'size': t_part[1],
                                                                                    'offset': t_part[0],
                                                                                    'keyslot': 0x03, 'type': 'enc'}
                            print('/twl_unk{}.img'.format(twl_part_fstype))
                            twl_part_fstype += 1

            else:
                if ncsd_part_fstype[idx] == 3:
                    # boot9 hardcoded this keyslot, i'll do this properly later
                    self.files['/firm{}.bin'.format(firm_idx)] = {'size': part[1], 'offset': part[0], 'keyslot': 0x06,
                                                                  'type': 'enc'}
                    print('/firm{}.bin'.format(firm_idx))
                    firm_idx += 1

                elif ncsd_part_fstype[idx] == 1 and ncsd_part_crypttype[idx] >= 2:
                    ctrnand_keyslot = 0x04 if ncsd_part_crypttype[idx] == 2 else 0x05
                    self.files['/ctrnand_full.img'] = {'size': part[1], 'offset': part[0], 'keyslot': ctrnand_keyslot,
                                                       'type': 'enc'}
                    print('/ctrnand_full.img')
                    nand_fp.seek(part[0])
                    iv = self.ctr + (part[0] >> 4)
                    ctr_mbr = self.crypto.aes_ctr(ctrnand_keyslot, iv, nand_fp.read(0x200))[0x1BE:0x1FE]
                    ctr_partitions = [[readle(ctr_mbr[i + 8:i + 12]) * 0x200,
                                       readle(ctr_mbr[i + 12:i + 16]) * 0x200]
                                      for i in range(0, 0x40, 0x10)]
                    ctr_part_fstype = 0
                    for c_idx, c_part in enumerate(ctr_partitions):
                        if c_part[0] != 0:
                            print('ctr  idx:{0}                      offset:{1:08x} size:{2[1]:08x} '
                                  .format(c_idx, part[0] + c_part[0], c_part), end='')
                            if ctr_part_fstype == 0:
                                self.files['/ctrnand_fat.img'] = {'size': c_part[1], 'offset': part[0] + c_part[0],
                                                                  'keyslot': ctrnand_keyslot, 'type': 'enc'}
                                print('/ctrnand_fat.img')
                                ctr_part_fstype += 1
                            else:
                                self.files['/ctr_unk{}.img'.format(ctr_part_fstype)] = {'size': c_part[1],
                                                                                        'offset': part[0] + c_part[0],
                                                                                        'keyslot': ctrnand_keyslot,
                                                                                        'type': 'enc'}
                                print('/ctr_unk{}.img'.format(ctr_part_fstype))
                                ctr_part_fstype += 1

                elif ncsd_part_fstype[idx] == 4:
                    self.files['/agbsave.bin'] = {'size': part[1], 'offset': part[0], 'keyslot': 0x07, 'type': 'enc'}
                    print('/agbsave.bin')

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
                # noinspection PyTypeChecker
                self.exefs_fuse = ExeFSMount(exefs_vfp, g_stat=g_stat)
                self.exefs_fuse.init('/')
                self._essentials_mounted = True
            except Exception as e:
                print("Failed to mount essential.exefs: {}: {}".format(type(e).__name__, e))

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
                st = {'st_mode': (S_IFREG | (0o444 if (self.readonly or path == '/_nandinfo.txt') else 0o666)),
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
            iv = (self.ctr if fi['keyslot']> 0x03 else self.ctr_twl) + (real_offset >> 4)
            data = self.crypto.aes_ctr(fi['keyslot'], iv, data)[before:len(data) - after]

        elif fi['type'] in {'keysect', 'twlmbr', 'info'}:
            # being lazy here since twlmbr starts at a weird offset. i'll do
            #   it properly some day. maybe.
            data = fi['content'][offset:offset + size]

        else:
            from pprint import pformat
            print('--------------------------------------------------',
                  'Warning: unknown file type (this should not happen!)',
                  'Please file an issue or contact the developer with the details below.',
                  '  https://github.com/ihaveamac/fuse-3ds/issues',
                  '--------------------------------------------------',
                  '{!r}: {!r}'.format(path, pformat(fi)), sep='\n')

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
            # thanks Stary2001
            size = real_len
            before = offset % 16
            after = (offset + size) % 16
            data = (b'\0' * before) + data + (b'\0' * after)
            iv = (self.ctr if fi['keyslot'] > 0x03 else self.ctr_twl) + (real_offset >> 4)
            data = self.crypto.aes_ctr(fi['keyslot'], iv, data)[before:len(data) - after]
            self.f.seek(real_offset)
            self.f.write(data)

        elif fi['type'] == 'twlmbr':
            twlmbr = bytearray(fi['content'])
            twlmbr[offset:offset + len(data)] = data
            final = bytes(twlmbr)
            self.f.seek(fi['offset'])
            self.f.write(self.crypto.aes_ctr(fi['keyslot'], self.ctr_twl + 0x1B, bytes(0xE) + final)[0xE:0x50])
            fi['content'] = final

        elif fi['type'] == 'keysect':
            keysect = bytearray(fi['content'])
            keysect[offset:offset + len(data)] = data
            final = bytes(keysect)
            cipher_keysect = AES.new(self.keysect_key, AES.MODE_ECB)
            self.f.seek(fi['offset'])
            self.f.write(cipher_keysect.encrypt(final))
            fi['content'] = final

        return real_len


def main(prog: str = None, args: list = None):
    if args is None:
        args = argv[1:]
    parser = ArgumentParser(prog=prog, description='Mount Nintendo 3DS NAND images.',
                            parents=(_c.default_argp, _c.readonly_argp, _c.dev_argp,
                                     _c.main_positional_args('nand', "NAND image")))
    parser.add_argument('--otp', help='path to otp (enc/dec); not needed if NAND image has essentials backup from '
                                      'GodMode9')
    parser.add_argument('--cid', help='NAND CID; not needed if NAND image has essentials backup from GodMode9')

    a = parser.parse_args(args)
    opts = dict(_c.parse_fuse_opts(a.o))

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    nand_stat = os.stat(a.nand)

    with open(a.nand, 'r{}b'.format('' if a.ro else '+')) as f:
        # noinspection PyTypeChecker
        mount = NANDImageMount(nand_fp=f, dev=a.dev, g_stat=nand_stat, readonly=a.ro, otp=a.otp, cid=a.cid)
        if _c.macos or _c.windows:
            opts['fstypename'] = 'NAND'
            # assuming / is the path separator since macos. but if windows gets support for this,
            #   it will have to be done differently.
            if _c.macos:
                path_to_show = os.path.realpath(a.nand).rsplit('/', maxsplit=2)
                opts['volname'] = "Nintendo 3DS NAND ({}/{})".format(path_to_show[-2], path_to_show[-1])
            elif _c.windows:
                # volume label can only be up to 32 chars
                # TODO: maybe I should show the path here, if i can shorten it properly
                opts['volname'] = "Nintendo 3DS NAND"
        FUSE(mount, a.mount_point, foreground=a.fg or a.do or a.d, ro=a.ro, nothreads=True, debug=a.d,
             fsname=os.path.realpath(a.nand).replace(',', '_'), **opts)


if __name__ == '__main__':
    print('Note: You should be calling this script as "mount_{0}" or "{1} -mfuse3ds {0}" '
          'instead of calling it directly.'.format('nand', _c.python_cmd))
    main()
