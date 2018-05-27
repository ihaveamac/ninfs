from functools import wraps
from hashlib import sha256
from os import environ
from os.path import isfile, getsize, join as pjoin
from typing import TYPE_CHECKING

from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter

from .common import PyCTRError
from .util import config_dirs, readbe, readle

if TYPE_CHECKING:
    # noinspection PyProtectedMember
    from Cryptodome.Cipher._mode_cbc import CbcMode
    from typing import Dict, Union

__all__ = ['CryptoError', 'KeyslotMissingError', 'BootromNotFoundError', 'CTRCrypto']


class CryptoError(PyCTRError):
    """Generic exception for cryptography operations."""


class OTPLengthError(CryptoError):
    """OTP is the wrong length."""


class CorruptOTPError(CryptoError):
    """OTP hash does not match."""


class KeyslotMissingError(CryptoError):
    """Normal key is not set up for the keyslot."""


# wonder if I'm doing this right...
class BootromNotFoundError(CryptoError):
    """ARM9 bootROM was not found. Main argument is a tuple of checked paths."""


base_key_x = {
    # New3DS 9.3 NCCH
    0x18: (0x82E9C9BEBFB8BDB875ECC0A07D474374, 0x304BF1468372EE64115EBD4093D84276),
    # New3DS 9.6 NCCH
    0x1B: (0x45AD04953992C7C893724A9A7BCE6182, 0x6C8B2944A0726035F941DFC018524FB6),
    # 7x NCCH
    0x25: (0xCEE7D8AB30C00DAE850EF5E382AC5AF3, 0x81907A4B6F1B47323A677974CE4AD71B),
}

# global values to be copied to new CTRCrypto instances after the first one
_b9_key_x = {}
_b9_key_y = {}
_b9_extdata_otp: bytes = None
_b9_extdata_keygen: bytes = None
_otp_key: bytes = None
_otp_iv: bytes = None

b9_paths = (['boot9.bin', 'boot9_prot.bin'] + [pjoin(x, 'boot9.bin') for x in config_dirs]
            + [pjoin(x, 'boot9_prot.bin') for x in config_dirs])
try:
    b9_paths.insert(0, environ['BOOT9_PATH'])
except KeyError:
    pass


def _requires_bootrom(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self.b9_keys_set:
            raise KeyslotMissingError('bootrom is required to set up keys, see setup_keys_from_boot9')
        return method(self, *args, **kwargs)
    return wrapper


# used from http://www.falatic.com/index.php/108/python-and-bitwise-rotation
# converted to def because pycodestyle complained to me
def rol(val: int, r_bits: int, max_bits: int) -> int:
    return (val << r_bits % max_bits) & (2 ** max_bits - 1) |\
           ((val & (2 ** max_bits - 1)) >> (max_bits - (r_bits % max_bits)))


class CTRCrypto:
    """Class for 3DS crypto operations, including encryption and key generation."""

    b9_keys_set: bool = False

    _b9_extdata_otp: bytes = None
    _b9_extdata_keygen: bytes = None

    _otp_key: bytes = None
    _otp_iv: bytes = None

    common_key_y = (
        # eShop
        (0xD07B337F9CA4385932A2E25723232EB9, 0x85215E96CB95A9ECA4B4DE601CB562C7),
        # System
        (0x0C767230F0998F1C46828202FAACBE4C,) * 2,
        # Unknown
        (0xC475CB3AB8C788BB575E12A10907B8A4,) * 2,
        # Unknown
        (0xE486EEE3D0C09C902F6686D4C06F649F,) * 2,
        # Unknown
        (0xED31BA9C04B067506C4497A35B7804FC,) * 2,
        # Unknown
        (0x5E66998AB4E8931606850FD7A16DD755,) * 2
    )

    def __init__(self, dev: int = 0, setup_b9_keys: bool = True):
        self.key_x: Dict[int, int] = {}
        self.key_y: Dict[int, int] = {0x03: 0xE1A00005202DDD1DBD4DC4D30AB9DC76,
                                      0x05: 0x4D804F4E9990194613A204AC584460BE}
        self.key_normal: Dict[int, bytes] = {}

        self.dev = dev

        for keyslot, keys in base_key_x.items():
            self.key_x[keyslot] = keys[dev]

        if setup_b9_keys:
            self.setup_keys_from_boot9()

    @property
    @_requires_bootrom
    def b9_extdata_otp(self) -> bytes:
        return self._b9_extdata_otp

    @property
    @_requires_bootrom
    def b9_extdata_keygen(self) -> bytes:
        return self._b9_extdata_keygen

    @property
    @_requires_bootrom
    def otp_key(self) -> bytes:
        return self._otp_key

    @property
    @_requires_bootrom
    def otp_iv(self) -> bytes:
        return self._otp_iv

    def create_cbc_cipher(self, keyslot: int, iv: bytes) -> 'CbcMode':
        """Create AES-CBC cipher with the given keyslot."""
        try:
            key = self.key_normal[keyslot]
        except KeyError:
            raise KeyslotMissingError(f'normal key for keyslot 0x{keyslot:02x} is not set up')

        return AES.new(key, AES.MODE_CBC, iv)

    def cbc_decrypt(self, keyslot: int, iv: bytes, data: bytes) -> bytes:
        """Do AES-CBC crypto with the given keyslot and data."""
        # TODO: remove this
        return self.create_cbc_cipher(keyslot, iv).decrypt(data)

    def aes_ctr(self, keyslot: int, ctr: int, data: bytes) -> bytes:
        """
        Do AES-CTR crypto with the given keyslot and data.

        Normal and DSi crypto will be automatically chosen depending on keyslot.
        """
        # TODO: make create_ctr_cipher
        try:
            key = self.key_normal[keyslot]
        except KeyError:
            raise KeyslotMissingError(f'normal key for keyslot 0x{keyslot:02x} is not set up')

        counter = Counter.new(128, initial_value=ctr)
        cipher = AES.new(key, AES.MODE_CTR, counter=counter)
        if keyslot < 0x04:
            # setup for DSi crypto
            data_len = len(data)
            data_rev = bytearray(data_len)
            for i in range(0, data_len, 0x10):
                data_rev[i:i + 0x10] = data[i:i + 0x10][::-1]

            data_out = bytearray(cipher.encrypt(bytes(data_rev)))

            for i in range(0, data_len, 0x10):
                data_out[i:i + 0x10] = data_out[i:i + 0x10][::-1]
            return bytes(data_out[0:data_len])

        else:
            # normal crypto for 3DS
            return cipher.encrypt(data)

    def set_keyslot(self, xy: str, keyslot: int, key: 'Union[int, bytes]'):
        """Sets a keyslot to the specified key."""
        to_use = None
        if xy == 'x':
            to_use = self.key_x
        elif xy == 'y':
            to_use = self.key_y
        if isinstance(key, bytes):
            key = int.from_bytes(key, 'big' if keyslot > 0x03 else 'little')
        to_use[keyslot] = key
        try:
            self.key_normal[keyslot] = self.keygen(keyslot)
        except KeyError:
            pass

    def set_normal_key(self, keyslot: int, key: bytes):
        self.key_normal[keyslot] = key

    def keygen(self, keyslot: int) -> bytes:
        """Generate a normal key based on the keyslot."""
        if keyslot < 0x04:
            # DSi
            return rol((self.key_x[keyslot] ^ self.key_y[keyslot]) + 0xFFFEFB4E295902582A680F5F1A4F3E79,
                       42, 128).to_bytes(0x10, 'big')
        else:
            # 3DS
            return rol((rol(self.key_x[keyslot], 2, 128) ^ self.key_y[keyslot]) + 0x1FF9E9AAC5FE0408024591DC5D52768A,
                       87, 128).to_bytes(0x10, 'big')

    def get_common_key(self, index: int) -> int:
        return self.common_key_y[index][self.dev]

    @staticmethod
    def keygen_manual(key_x: int, key_y: int) -> bytes:
        """Generate a normal key using the 3DS AES keyscrambler."""
        return rol((rol(key_x, 2, 128) ^ key_y) + 0x1FF9E9AAC5FE0408024591DC5D52768A, 87, 128).to_bytes(0x10, 'big')

    @staticmethod
    def keygen_twl_manual(key_x: int, key_y: int) -> bytes:
        """Generate a normal key using the DSi AES keyscrambler."""
        # usually would convert to LE bytes in the end then flip with [::-1], but those just cancel out
        return rol((key_x ^ key_y) + 0xFFFEFB4E295902582A680F5F1A4F3E79, 42, 128).to_bytes(0x10, 'big')

    def _copy_global_keys(self):
        self.key_x.update(_b9_key_x)
        self.key_y.update(_b9_key_y)
        self._otp_key = _otp_key
        self._otp_iv = _otp_iv
        self._b9_extdata_otp = _b9_extdata_otp
        self._b9_extdata_keygen = _b9_extdata_keygen

        self.b9_keys_set = True

    def setup_keys_from_boot9(self, path: str = None):
        """Set up certain keys from the ARM9 bootROM."""
        global _otp_key, _otp_iv, _b9_extdata_otp, _b9_extdata_keygen
        if self.b9_keys_set:
            return

        if _b9_key_x:
            self._copy_global_keys()
            return

        # TODO: set up all relevant keys

        if path:
            paths = (path,)
        else:
            paths = b9_paths
        for p in paths:
            if isfile(p):
                keyblob_offset = 0x5860
                otp_key_offset = 0x56E0
                if self.dev:
                    keyblob_offset += 0x400
                    otp_key_offset += 0x20
                if getsize(p) == 0x10000:
                    keyblob_offset += 0x8000
                    otp_key_offset += 0x8000

                with open(p, 'rb') as b9:
                    b9.seek(otp_key_offset)
                    _otp_key = b9.read(0x10)
                    _otp_iv = b9.read(0x10)

                    b9.seek(keyblob_offset)
                    _b9_extdata_keygen = b9.read(0x200)
                    _b9_extdata_otp = _b9_extdata_keygen[0:0x24]

                    # Original NCCH
                    b9.seek(keyblob_offset + 0x170)
                    _b9_key_x[0x2C] = readbe(b9.read(0x10))

                    # SD key
                    b9.seek(keyblob_offset + 0x190)
                    _b9_key_x[0x34] = readbe(b9.read(0x10))
                    _b9_key_x[0x35] = _b9_key_x[0x34]

                    # Common key
                    b9.seek(keyblob_offset + 0x1C0)
                    _b9_key_x[0x3D] = readbe(b9.read(0x10))

                    # NAND keys
                    b9.seek(keyblob_offset + 0x1F0)
                    _b9_key_y[0x04] = readbe(b9.read(0x10))
                    b9.seek(0x10, 1)
                    _b9_key_y[0x06] = readbe(b9.read(0x10))
                    _b9_key_y[0x07] = readbe(b9.read(0x10))

                self._copy_global_keys()
                return

        # if keys are not set...
        raise BootromNotFoundError(paths)

    @_requires_bootrom
    def setup_keys_from_otp(self, otp: bytes):
        """Set up console-unique keys from an OTP dump. Encrypted and decrypted are supported."""
        otp_len = len(otp)
        if otp_len != 0x100:
            raise OTPLengthError(otp_len)

        cipher_otp = AES.new(self.otp_key, AES.MODE_CBC, self.otp_iv)
        if otp[0:4] == b'\x0f\xb0\xad\xde':
            # decrypted otp
            otp_enc: bytes = cipher_otp.encrypt(otp)
            otp_dec = otp
        else:
            # encrypted otp
            otp_enc = otp
            otp_dec: bytes = cipher_otp.decrypt(otp)

        otp_hash: bytes = otp_dec[0xE0:0x100]
        otp_hash_digest: bytes = sha256(otp_dec[0:0xE0]).digest()
        if otp_hash_digest != otp_hash:
            raise CorruptOTPError(f'expected: {otp_hash.hex()}; result: {otp_hash_digest.hex()}')

        otp_keysect_hash: bytes = sha256(otp_enc[0:0x90]).digest()

        self.set_keyslot('x', 0x11, otp_keysect_hash[0:0x10])
        self.set_keyslot('y', 0x11, otp_keysect_hash[0:0x10])

        # most otp code from https://github.com/Stary2001/3ds_tools/blob/master/three_ds/aesengine.py

        twl_cid_lo, twl_cid_hi = readle(otp_dec[0x08:0xC]), readle(otp_dec[0xC:0x10])
        twl_cid_lo ^= 0xB358A6AF
        twl_cid_lo |= 0x80000000
        twl_cid_hi ^= 0x08C267B7
        twl_cid_lo = twl_cid_lo.to_bytes(4, 'little')
        twl_cid_hi = twl_cid_hi.to_bytes(4, 'little')
        self.set_keyslot('x', 0x03, twl_cid_lo + b'NINTENDO' + twl_cid_hi)

        console_key_xy: bytes = sha256(otp_dec[0x90:0xAC] + self.b9_extdata_otp).digest()
        self.set_keyslot('x', 0x3F, console_key_xy[0:0x10])
        self.set_keyslot('y', 0x3F, console_key_xy[0x10:0x20])

        extdata_off = 0

        def gen(n: int) -> bytes:
            nonlocal extdata_off
            extdata_off += 36
            iv = self.b9_extdata_keygen[extdata_off:extdata_off+16]
            extdata_off += 16

            data = self.create_cbc_cipher(0x3F, iv).encrypt(self.b9_extdata_keygen[extdata_off:extdata_off + 64])

            extdata_off += n
            return data

        a = gen(64)
        for i in range(0x4, 0x8):
            self.set_keyslot('x', i, a[0:16])

        for i in range(0x8, 0xc):
            self.set_keyslot('x', i, a[16:32])

        for i in range(0xc, 0x10):
            self.set_keyslot('x', i, a[32:48])

        self.set_keyslot('x', 0x10, a[48:64])

        b = gen(16)
        off = 0
        for i in range(0x14, 0x18):
            self.set_keyslot('x', i, b[off:off + 16])
            off += 16

        c = gen(64)
        for i in range(0x18, 0x1c):
            self.set_keyslot('x', i, c[0:16])

        for i in range(0x1c, 0x20):
            self.set_keyslot('x', i, c[16:32])

        for i in range(0x20, 0x24):
            self.set_keyslot('x', i, c[32:48])

        self.set_keyslot('x', 0x24, c[48:64])

        d = gen(16)
        off = 0

        for i in range(0x28, 0x2c):
            self.set_keyslot('x', i, d[off:off + 16])
            off += 16

    @_requires_bootrom
    def setup_keys_from_otp_file(self, path: str):
        """Set up console-unique keys from an OTP file. Encrypted and decrypted are supported."""
        with open(path, 'rb') as f:
            self.setup_keys_from_otp(f.read(0x100))
