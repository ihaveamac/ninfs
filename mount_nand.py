#!/usr/bin/env python3

import argparse
import errno
import hashlib
import logging
import os
import pprint
import stat
import struct
import sys

try:
    from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
except ImportError:
    sys.exit('fuse module not found, please install fusepy to mount images (`pip install fusepy`).')

try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
except ImportError:
    sys.exit('Cryptodome module not found, please install pycryptodomex for encryption support (`pip install pycryptodomex`).')

# ncsd image doesn't have the actual size
nand_size = {0x200000: 0x3AF00000, 0x280000: 0x4D800000}


# used from http://www.falatic.com/index.php/108/python-and-bitwise-rotation
# converted to def because pycodestyle complained to me
def rol(val, r_bits, max_bits):
    return (val << r_bits % max_bits) & (2 ** max_bits - 1) | ((val & (2 ** max_bits - 1)) >> (max_bits - (r_bits % max_bits)))


def keygen(key_x, key_y):
    return rol((rol(key_x, 2, 128) ^ key_y) + 0x1FF9E9AAC5FE0408024591DC5D52768A, 87, 128).to_bytes(0x10, 'big')


class NANDImage(LoggingMixIn, Operations):
    def __init__(self):
        keys_set = False
        keyslots_y = {}
        otp_key = b''
        otp_iv = b''
        boot9_extdata_keygen = b''
        boot9_extdata_keygen_iv = b''
        boot9_extdata_otp = b''

        def check_b9_file(path):
            nonlocal keys_set, keyslots_y, otp_key, otp_iv, boot9_extdata_keygen, boot9_extdata_keygen_iv, boot9_extdata_otp
            if not keys_set:
                if os.path.isfile(path):
                    keyblob_offset = 0x5860
                    otp_key_offset = 0x56E0
                    if a.dev:
                        keyblob_offset += 0x4000
                        otp_key_offset += 0x20
                    if os.path.getsize(path) == 0x10000:
                        keyblob_offset += 0x8000
                        otp_key_offset += 0x8000
                    with open(path, 'rb') as b9:
                        b9.seek(keyblob_offset)
                        boot9_extdata_otp = b9.read(0x24)
                        boot9_extdata_keygen = b9.read(0x10)
                        boot9_extdata_keygen_iv = b9.read(0x10)
                        b9.seek(keyblob_offset + 0x1F0)
                        keyslots_y[0x04] = b9.read(0x10)
                        # not so easy to avoid
                        keyslots_y[0x05] = bytes.fromhex('4D804F4E9990194613A204AC584460BE')
                        b9.seek(0x10, 1)
                        keyslots_y[0x06] = b9.read(0x10)
                        keyslots_y[0x07] = b9.read(0x10)
                        b9.seek(otp_key_offset)
                        otp_key = b9.read(0x10)
                        otp_iv = b9.read(0x10)
                    keys_set = True

        check_b9_file('boot9.bin')
        check_b9_file('boot9_prot.bin')
        check_b9_file(os.path.expanduser('~') + '/.3ds/boot9.bin')
        check_b9_file(os.path.expanduser('~') + '/.3ds/boot9_prot.bin')

        if not keys_set:
            sys.exit('Failed to get keys from boot9')

        self.f = open(a.nand, 'r{}b'.format('' if a.ro else '+'))
        self.f.seek(0x100)  # screw the signature
        ncsd_header = self.f.read(0x100)
        if ncsd_header[0:4] != b'NCSD':
            sys.exit('NCSD magic not found, is this a real Nintendo 3DS NAND image?')
        media_id = ncsd_header[0x8:0x10]
        if media_id != b'\0' * 8:
            sys.exit('Media ID not all-zero, is this a real Nintendo 3DS NAND image?')

        # check for essentials.exefs
        self.f.seek(0x200)
        essentials_headers_raw = self.f.read(0xA0)  # doesn't include hash
        if a.otp or a.cid:
            if a.otp:
                with open(a.otp, 'rb') as f:
                    otp = f.read(0x200)
            else:
                sys.exit('OTP not found, provide otp-file with --otp (or embed essentials backup with GodMode9)')
            if a.cid:
                self.ctr = int.from_bytes(hashlib.sha256(bytes.fromhex(a.cid)).digest()[0:16], 'big')
            else:
                sys.exit('NAND CID not found, provide cid with --cid (or embed essentials backup with GodMode9)')
        else:
            if essentials_headers_raw == b'\0' * 0xA0 or essentials_headers_raw == b'\xFF' * 0xA0:
                if not a.otp:
                    sys.exit('OTP not found, provide otp-file with --otp (or embed essentials backup with GodMode9)')
                if not a.cid:
                    sys.exit('NAND CID not found, provide cid with --cid (or embed essentials backup with GodMode9)')
            else:
                essentials_headers = [[essentials_headers_raw[i:i + 8].decode('utf-8').rstrip('\0'),
                                       int.from_bytes(essentials_headers_raw[i + 8:i + 12], 'little'),
                                       int.from_bytes(essentials_headers_raw[i + 12:i + 16], 'little')] for i in range(0, 0xA0, 0x10)]
                for header in essentials_headers:
                    if header[0] == 'otp':
                        self.f.seek(0x400 + header[1])
                        otp = self.f.read(header[2])
                    elif header[0] == 'nand_cid':
                        self.f.seek(0x400 + header[1])
                        cid = self.f.read(header[2])
                        self.ctr = int.from_bytes(hashlib.sha256(cid[0:16]).digest()[0:16], 'big')
                if not (otp or cid):
                    sys.exit('otp and nand_cid somehow not found in essentials backup. update with GodMode9 or provide OTP/NAND CID with --otp/--cid.')

        cipher_otp = AES.new(otp_key, AES.MODE_CBC, otp_iv)
        if otp[0:4][::-1] == b'\xDE\xAD\xB0\x0F':
            otp_enc = cipher_otp.encrypt(otp)
            otp_keysect_hash = hashlib.sha256(otp_enc[0:0x90]).digest()
        else:
            otp_keysect_hash = hashlib.sha256(otp[0:0x90]).digest()
            otp = cipher_otp.decrypt(otp)

        # only keys for slots 0x04-0x07 are used, and keyX for all of them are
        #   the same, so this only uses the data needed for this key
        # thanks Stary2001 (from 3ds_tools)
        tmp_otp_data = otp[0x90:0xAC] + boot9_extdata_otp
        console_keyxy = hashlib.sha256(tmp_otp_data).digest()
        console_normalkey = keygen(int.from_bytes(console_keyxy[0:16], 'big'), int.from_bytes(console_keyxy[16:32], 'big'))

        cipher_keygen = AES.new(console_normalkey, AES.MODE_CBC, boot9_extdata_keygen_iv)
        key_x = cipher_keygen.encrypt(boot9_extdata_keygen)

        # starting at 0x04
        self.keyslots = {
            0x04: keygen(int.from_bytes(key_x, 'big'), int.from_bytes(keyslots_y[0x04], 'big')),
            0x05: keygen(int.from_bytes(key_x, 'big'), int.from_bytes(keyslots_y[0x05], 'big')),
            0x06: keygen(int.from_bytes(key_x, 'big'), int.from_bytes(keyslots_y[0x06], 'big')),
            0x07: keygen(int.from_bytes(key_x, 'big'), int.from_bytes(keyslots_y[0x07], 'big'))
        }

        nand_stat = os.stat(a.nand)
        self.g_stat = {}
        self.g_stat['st_ctime'] = int(nand_stat.st_ctime)
        self.g_stat['st_mtime'] = int(nand_stat.st_mtime)
        self.g_stat['st_atime'] = int(nand_stat.st_atime)

        self.real_nand_size = nand_size[int.from_bytes(ncsd_header[4:8], 'little')]

        self.files = {}
        self.files['/nand_hdr.bin'] = {'size': 0x200, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'}
        self.files['/nand.bin'] = {'size': nand_stat.st_size, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'}
        self.files['/nand_minsize.bin'] = {'size': self.real_nand_size, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'}

        self.f.seek(0x12C00)
        keysect_enc = self.f.read(0x200)
        if keysect_enc != b'\0' * 0x200 and keysect_enc != b'\xFF' * 0x200:
            keysect_x = otp_keysect_hash[0:16]
            keysect_y = otp_keysect_hash[16:32]
            self.keysect_key = keygen(int.from_bytes(keysect_x, 'big'), int.from_bytes(keysect_y, 'big'))
            cipher_keysect = AES.new(self.keysect_key, AES.MODE_ECB)
            keysect_dec = cipher_keysect.decrypt(keysect_enc)
            # i'm cheating here by putting the decrypted version in memory and
            #   not reading from the image every time. but it's not AES-CTR so
            #   fuck that.
            self.files['/sector0x96.bin'] = {'size': 0x200, 'offset': 0x12C00, 'keyslot': 0xFF, 'type': 'keysect', 'content': keysect_dec}

        part_fstype = ncsd_header[0x10:0x18]
        part_crypttype = ncsd_header[0x18:0x20]
        part_raw = ncsd_header[0x20:0x60]
        partitions = [[int.from_bytes(part_raw[i:i + 4], 'little') * 0x200,
                       int.from_bytes(part_raw[i + 4:i + 8], 'little') * 0x200] for i in range(0, 0x40, 0x8)]

        firm_idx = 0
        for idx, part in enumerate(partitions[1:]):  # ignoring the twl area for now
            idx += 1
            # if part_fstype[idx] != 0:
            #     print('ctr idx:{0} fstype:{1} crypttype:{2} offset:{3[0]:08x} size:{3[1]:08x}'.format(idx, part_fstype[idx], part_crypttype[idx], part))
            if part_fstype[idx] == 3:
                self.files['/firm{}.bin'.format(firm_idx)] = {'size': part[1], 'offset': part[0], 'keyslot': 0x06, 'type': 'ctr'}  # boot9 hardcoded this keyslot, i'll do this properly later
                firm_idx += 1
            elif part_fstype[idx] == 1 and part_crypttype[idx] >= 2:
                ctrn_mbr_size = 0x2CA00 if part_crypttype[idx] == 2 else 0x2AE00
                ctrn_keyslot = 0x04 if part_crypttype[idx] == 2 else 0x05
                self.files['/ctrnand_fat.img'] = {'size': part[1] - ctrn_mbr_size, 'offset': part[0] + ctrn_mbr_size, 'keyslot': ctrn_keyslot, 'type': 'ctr'}
                self.files['/ctrnand_full.img'] = {'size': part[1], 'offset': part[0], 'keyslot': ctrn_keyslot, 'type': 'ctr'}
            elif part_fstype[idx] == 4:
                self.files['/agbsave.bin'] = {'size': part[1], 'offset': part[0], 'keyslot': 0x07, 'type': 'ctr'}

        self.fd = 0

    def __del__(self):
        print('closing')
        self.f.close()

    def getattr(self, path, fh=None):
        if path == '/':
            st = {'st_mode': (stat.S_IFDIR | (0o555 if a.ro else 0o755)), 'st_nlink': 2}
        elif path in self.files:
            st = {'st_mode': (stat.S_IFREG | (0o444 if a.ro else 0o644)), 'st_size': self.files[path]['size'], 'st_nlink': 1}
        else:
            raise FuseOSError(errno.ENOENT)
        return {**st, **self.g_stat}

    def getxattr(self, path, name, position=0):
        attrs = self.getattr(path)
        try:
            return str(attrs[name])
        except KeyError:
            raise FuseOSError(errno.ENOATTR)

    def listxattr(self, path):
        attrs = self.getattr(path)
        try:
            return attrs.keys()
        except KeyError:
            raise FuseOSError(errno.ENOATTR)

    def statfs(self, path):
        return {'f_bsize': 4096, 'f_blocks': self.real_nand_size // 4096, 'f_bavail': 0, 'f_bfree': 0}

    def open(self, path, flags):
        # wat?
        self.fd += 1
        return self.fd

    def readdir(self, path, fh):
        return ['.', '..'] + [x[1:] for x in self.files]

    def read(self, path, size, offset, fh):
        fi = self.files[path]
        real_offset = fi['offset'] + offset
        if fi['type'] == 'raw':
            self.f.seek(real_offset)
            data = self.f.read(size)

        elif fi['type'] == 'ctr':
            self.f.seek(real_offset)
            data = self.f.read(size)
            # thanks Stary2001
            before = offset % 16
            after = (offset + size) % 16
            if size % 16 != 0:
                size = size + 16 - size % 16
            data = (b'\0' * before) + data + (b'\0' * after)
            iv = self.ctr + (real_offset >> 4)
            counter = Counter.new(128, initial_value=iv)
            cipher = AES.new(self.keyslots[fi['keyslot']], AES.MODE_CTR, counter=counter)
            data = cipher.decrypt(data)[before:len(data) - after]

        elif fi['type'] == 'twl':
            pass  # TODO: this

        elif fi['type'] == 'keysect':
            data = fi['content'][offset:offset + size]

        return data

    def write(self, path, data, offset, fh):
        fi = self.files[path]
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

        elif fi['type'] == 'ctr':
            # thanks Stary2001
            size = real_len
            before = offset % 16
            after = (offset + size) % 16
            if size % 16 != 0:
                size = size + 16 - size % 16
            data = (b'\0' * before) + data + (b'\0' * after)
            iv = self.ctr + (real_offset >> 4)
            counter = Counter.new(128, initial_value=iv)
            cipher = AES.new(self.keyslots[fi['keyslot']], AES.MODE_CTR, counter=counter)
            data = cipher.encrypt(data)[before:len(data) - after]
            self.f.seek(real_offset)
            self.f.write(data)

        elif fi['type'] == 'twl':
            pass  # TODO: this

        elif fi['type'] == 'keysect':
            keysect = list(fi['content'])
            keysect[offset:offset + len(data)] = data
            cipher_keysect = AES.new(self.keysect_key, AES.MODE_ECB)
            self.f.seek(real_offset)
            final = bytes(keysect)
            self.f.write(cipher_keysect.encrypt(final))
            fi['content'] = final

        return real_len

    def truncate(self, path, length, fh=None):
        pass

    def unlink(self, path):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS NAND images.')
    parser.add_argument('--otp', help='path to otp (enc/dec); not needed if NAND image has essentials backup from GodMode9')
    parser.add_argument('--cid', help='NAND CID; not needed if NAND image has essentials backup from GodMode9')
    parser.add_argument('--dev', help='use dev keys', action='store_const', const=1, default=0)
    parser.add_argument('--ro', help='mount read-only', action='store_true')
    parser.add_argument('nand', help='NAND image')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()

    # logging.basicConfig(level=logging.DEBUG)
    fuse = FUSE(NANDImage(), a.mount_point, foreground=True, ro=a.ro)
