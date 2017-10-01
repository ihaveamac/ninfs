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


def keygen_twl(key_x, key_y):
    # usually would convert to LE bytes in the end then flip with [::-1], but those just cancel out
    return rol((key_x ^ key_y) + 0xFFFEFB4E295902582A680F5F1A4F3E79, 42, 128).to_bytes(0x10, 'big')


# taken from https://github.com/Stary2001/3ds_tools/blob/94614f3b80e6f4d32c5ec4596424dccfaad32774/three_ds/crypto_wrappers.py#L38-L50
def aes_ctr_dsi(key, ctr, data):
    data_len = len(data)

    data_rev = bytearray(data_len)
    # data_out = bytearray(data_len + 16)
    for i in range(0, len(data), 0x10):
        data_rev[i:i + 0x10] = data[i:i + 0x10][::-1]

    counter = Counter.new(128, initial_value=ctr)
    cipher = AES.new(key, AES.MODE_CTR, counter=counter)

    data_out = bytearray(cipher.encrypt(bytes(data_rev)))

    for i in range(0, data_len, 0x10):
        data_out[i:i + 0x10] = data_out[i:i + 0x10][::-1]
    return bytes(data_out[0:data_len])


class NANDImage(LoggingMixIn, Operations):
    fd = 0

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
                        keyblob_offset += 0x400
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

        # check for essential.exefs
        self.f.seek(0x200)
        essentials_headers_raw = self.f.read(0xA0)  # doesn't include hash
        if a.otp or a.cid:
            if a.otp:
                with open(a.otp, 'rb') as f:
                    otp = f.read(0x200)
            else:
                sys.exit('OTP not found, provide otp-file with --otp (or embed essentials backup with GodMode9)')
            if a.cid:
                cid_hex = bytes.fromhex(a.cid)
                self.ctr = int.from_bytes(hashlib.sha256(cid_hex).digest()[0:16], 'big')
                # self.ctr_twl = int.from_bytes(hashlib.sha1(cid_hex).digest()[16:0:-1], 'big')
                self.ctr_twl = int.from_bytes(hashlib.sha1(cid_hex).digest()[0:16], 'little')
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
                        self.ctr = int.from_bytes(hashlib.sha256(cid).digest()[0:16], 'big')
                        self.ctr_twl = int.from_bytes(hashlib.sha1(cid).digest()[0:16], 'little')
                if not (otp or cid):
                    sys.exit('otp and nand_cid somehow not found in essentials backup. update with GodMode9 or provide OTP/NAND CID with --otp/--cid.')

        cipher_otp = AES.new(otp_key, AES.MODE_CBC, otp_iv)
        if otp[0:4][::-1] == b'\xDE\xAD\xB0\x0F':
            otp_enc = cipher_otp.encrypt(otp)
            otp_keysect_hash = hashlib.sha256(otp_enc[0:0x90]).digest()
        else:
            otp_keysect_hash = hashlib.sha256(otp[0:0x90]).digest()
            otp = cipher_otp.decrypt(otp)

        # generate twl keys
        twl_cid_lo, twl_cid_hi = struct.unpack("II", otp[0x08:0x10])
        twl_cid_lo ^= 0xB358A6AF
        twl_cid_lo |= 0x80000000
        twl_cid_hi ^= 0x08C267B7
        twl_cid_lo = struct.pack("I", twl_cid_lo)
        twl_cid_hi = struct.pack("I", twl_cid_hi)

        twl_keyx = twl_cid_lo + b'NINTENDO' + twl_cid_hi
        twl_keyy = bytes.fromhex('76DCB90AD3C44DBD1DDD2D200500A0E1')
        twl_normalkey = keygen_twl(int.from_bytes(twl_keyx, 'little'), int.from_bytes(twl_keyy, 'little'))

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
            0x03: twl_normalkey,
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

        self.f.seek(0, 2)
        raw_nand_size = self.f.tell()

        self.real_nand_size = nand_size[int.from_bytes(ncsd_header[4:8], 'little')]

        self.files = {}
        self.files['/nand_hdr.bin'] = {'size': 0x200, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'}
        self.files['/nand.bin'] = {'size': raw_nand_size, 'offset': 0, 'keyslot': 0xFF, 'type': 'raw'}
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

        ncsd_part_fstype = ncsd_header[0x10:0x18]
        ncsd_part_crypttype = ncsd_header[0x18:0x20]
        ncsd_part_raw = ncsd_header[0x20:0x60]
        ncsd_partitions = [[int.from_bytes(ncsd_part_raw[i:i + 4], 'little') * 0x200,
                            int.from_bytes(ncsd_part_raw[i + 4:i + 8], 'little') * 0x200] for i in range(0, 0x40, 0x8)]

        # including padding for crypto
        twl_mbr = aes_ctr_dsi(twl_normalkey, self.ctr_twl + 0x1B, ncsd_header[0xB0:0x100])[0xE:0x50]
        twl_partitions = [[int.from_bytes(twl_mbr[i + 8:i + 12], 'little') * 0x200,
                           int.from_bytes(twl_mbr[i + 12:i + 16], 'little') * 0x200] for i in range(0, 0x40, 0x10)]

        self.files['/twlmbr.bin'] = {'size': 0x42, 'offset': 0x1BE, 'keyslot': 0x03, 'type': 'twlmbr', 'content': twl_mbr}

        firm_idx = 0
        for idx, part in enumerate(ncsd_partitions):
            if ncsd_part_fstype[idx] == 0:
                continue
            print('ncsd idx:{0} fstype:{1} crypttype:{2} offset:{3[0]:08x} size:{3[1]:08x} '.format(idx, ncsd_part_fstype[idx], ncsd_part_crypttype[idx], part), end='')
            if idx == 0:
                print()
                twl_part_fstype = 0
                for t_idx, t_part in enumerate(twl_partitions):
                    if t_part[0] != 0:
                        print('twl  idx:{0}                      offset:{1[0]:08x} size:{1[1]:08x} '.format(t_idx, t_part), end='')
                        if twl_part_fstype == 0:
                            self.files['/twln.img'] = {'size': t_part[1], 'offset': t_part[0], 'keyslot': 0x03, 'type': 'twl'}
                            print('/twln.img')
                            twl_part_fstype += 1
                        elif twl_part_fstype == 1:
                            self.files['/twlp.img'] = {'size': t_part[1], 'offset': t_part[0], 'keyslot': 0x03, 'type': 'twl'}
                            print('/twlp.img')
                            twl_part_fstype += 1
                        else:
                            self.files['/twl_unk{}.img'.format(twl_part_fstype)] = {'size': t_part[1], 'offset': t_part[0], 'keyslot': 0x03, 'type': 'twl'}
                            print('/twl_unk{}.img'.format(twl_part_fstype))
                            twl_part_fstype += 1

            else:
                if ncsd_part_fstype[idx] == 3:
                    self.files['/firm{}.bin'.format(firm_idx)] = {'size': part[1], 'offset': part[0], 'keyslot': 0x06, 'type': 'ctr'}  # boot9 hardcoded this keyslot, i'll do this properly later
                    print('/firm{}.bin'.format(firm_idx))
                    firm_idx += 1

                elif ncsd_part_fstype[idx] == 1 and ncsd_part_crypttype[idx] >= 2:
                    ctrn_keyslot = 0x04 if ncsd_part_crypttype[idx] == 2 else 0x05
                    self.files['/ctrnand_full.img'] = {'size': part[1], 'offset': part[0], 'keyslot': ctrn_keyslot, 'type': 'ctr'}
                    print('/ctrnand_full.img')
                    self.f.seek(part[0])
                    iv = self.ctr + (part[0] >> 4)
                    counter = Counter.new(128, initial_value=iv)
                    cipher = AES.new(self.keyslots[ctrn_keyslot], AES.MODE_CTR, counter=counter)
                    ctr_mbr = cipher.decrypt(self.f.read(0x200))[0x1BE:0x1FE]
                    ctr_partitions = [[int.from_bytes(ctr_mbr[i + 8:i + 12], 'little') * 0x200,
                                       int.from_bytes(ctr_mbr[i + 12:i + 16], 'little') * 0x200] for i in range(0, 0x40, 0x10)]
                    ctr_part_fstype = 0
                    for c_idx, c_part in enumerate(ctr_partitions):
                        if c_part[0] != 0:
                            print('ctr  idx:{0}                      offset:{1:08x} size:{2[1]:08x} '.format(c_idx, part[0] + c_part[0], c_part), end='')
                            if ctr_part_fstype == 0:
                                self.files['/ctrnand_fat.img'] = {'size': c_part[1], 'offset': part[0] + c_part[0], 'keyslot': ctrn_keyslot, 'type': 'ctr'}
                                print('/ctrnand_fat.img')
                                ctr_part_fstype += 1
                            else:
                                self.files['/ctr_unk{}.img'.format(ctr_part_fstype)] = {'size': c_part[1], 'offset': part[0] + c_part[0], 'keyslot': ctrn_keyslot, 'type': 'ctr'}
                                print('/ctr_unk{}.img'.format(ctr_part_fstype))
                                ctr_part_fstype += 1
                        pass

                elif ncsd_part_fstype[idx] == 4:
                    self.files['/agbsave.bin'] = {'size': part[1], 'offset': part[0], 'keyslot': 0x07, 'type': 'ctr'}
                    print('/agbsave.bin')

        # GM9 bonus drive
        if raw_nand_size != self.real_nand_size:
            self.f.seek(self.real_nand_size)
            bonus_drive_header = self.f.read(0x200)
            if bonus_drive_header[0x1FE:0x200] == b'\x55\xAA':
                self.files['/bonus.img'] = {'size': raw_nand_size - self.real_nand_size, 'offset': self.real_nand_size, 'keyslot': 0xFF, 'type': 'raw'}

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
            st = {'st_mode': (stat.S_IFDIR | (0o555 if a.ro else 0o777)), 'st_nlink': 2}
        elif path.lower() in self.files:
            st = {'st_mode': (stat.S_IFREG | (0o444 if a.ro else 0o666)), 'st_size': self.files[path.lower()]['size'], 'st_nlink': 1}
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
            self.f.seek(real_offset)
            data = self.f.read(size)
            # thanks Stary2001
            before = offset % 16
            after = (offset + size) % 16
            if size % 16 != 0:
                size = size + 16 - size % 16
            data = (b'\0' * before) + data + (b'\0' * after)
            iv = self.ctr_twl + (real_offset >> 4)
            data = aes_ctr_dsi(self.keyslots[fi['keyslot']], iv, data)[before:len(data) - after]

        elif fi['type'] == 'keysect' or fi['type'] == 'twlmbr':
            # being lazy here since twlmbr starts at a weird offset. i'll do
            #   it prperly some day. maybe.
            data = fi['content'][offset:offset + size]

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
        return {'f_bsize': 4096, 'f_blocks': self.real_nand_size // 4096, 'f_bavail': 0, 'f_bfree': 0, 'f_files': len(self.files)}

    # unused
    def symlink(self, target, source):
        pass

    # unused
    # if this is set to None, some programs may crash.
    def truncate(self, path, length, fh=None):
        return None

    # unused
    def utimens(self, *args, **kwargs):
        return None

    # unused
    def unlink(self, path):
        return None

    def write(self, path, data, offset, fh):
        if readonly:
            # windows!!!!!!!
            raise FuseOSError(errno.EPERM)
        fi = self.files[path.lower()]
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
            # thanks Stary2001
            size = real_len
            before = offset % 16
            after = (offset + size) % 16
            if size % 16 != 0:
                size = size + 16 - size % 16
            data = (b'\0' * before) + data + (b'\0' * after)
            iv = self.ctr_twl + (real_offset >> 4)
            data = aes_ctr_dsi(self.keyslots[fi['keyslot']], iv, data)[before:len(data) - after]
            self.f.seek(real_offset)
            self.f.write(data)

        elif fi['type'] == 'twlmbr':
            twlmbr = bytearray(fi['content'])
            twlmbr[offset:offset + len(data)] = data
            final = bytes(twlmbr)
            self.f.seek(fi['offset'])
            self.f.write(aes_ctr_dsi(self.keyslots[fi['keyslot']], self.ctr_twl + 0x1B, bytes(0xE) + final)[0xE:0x50])
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mount Nintendo 3DS NAND images.')
    parser.add_argument('--otp', help='path to otp (enc/dec); not needed if NAND image has essentials backup from GodMode9')
    parser.add_argument('--cid', help='NAND CID; not needed if NAND image has essentials backup from GodMode9')
    parser.add_argument('--dev', help='use dev keys', action='store_const', const=1, default=0)
    parser.add_argument('--ro', help='mount read-only', action='store_true')
    parser.add_argument('--fg', '-f', help='run in foreground', action='store_true')
    parser.add_argument('--do', help='debug output (python logging module)', action='store_true')
    parser.add_argument('-o', metavar='OPTIONS', help='mount options')
    parser.add_argument('nand', help='NAND image')
    parser.add_argument('mount_point', help='mount point')

    a = parser.parse_args()
    try:
        opts = {o: True for o in a.o.split(',')}
    except AttributeError:
        opts = {}

    readonly = a.ro

    if a.do:
        logging.basicConfig(level=logging.DEBUG)

    fuse = FUSE(NANDImage(), a.mount_point, foreground=a.fg or a.do, fsname=os.path.realpath(a.nand), ro=readonly, **opts)
