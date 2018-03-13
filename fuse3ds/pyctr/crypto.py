from os.path import isfile, getsize
from typing import Dict

from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter

from . import util

__all__ = ['CryptoError', 'KeyslotMissingError', 'BootromNotFoundError', 'CTRCrypto']


class CryptoError(Exception):
    """Generic exception for cryptography operations."""


class KeyslotMissingError(CryptoError):
    """Normal key is not set up for the keyslot."""


# wonder if I'm doing this right...
class BootromNotFoundError(CryptoError):
    """ARM9 bootROM was not found."""


base_key_x = {
    # New3DS 9.3 NCCH
    0x18: (0x82E9C9BEBFB8BDB875ECC0A07D474374, 0x304BF1468372EE64115EBD4093D84276),
    # New3DS 9.6 NCCH
    0x1B: (0x45AD04953992C7C893724A9A7BCE6182, 0x6C8B2944A0726035F941DFC018524FB6),
    # 7x NCCH
    0x25: (0xCEE7D8AB30C00DAE850EF5E382AC5AF3, 0x81907A4B6F1B47323A677974CE4AD71B),
}


# used from http://www.falatic.com/index.php/108/python-and-bitwise-rotation
# converted to def because pycodestyle complained to me
def rol(val: int, r_bits: int, max_bits: int) -> int:
    return (val << r_bits % max_bits) & (2 ** max_bits - 1) |\
           ((val & (2 ** max_bits - 1)) >> (max_bits - (r_bits % max_bits)))


class CTRCrypto:
    """Class for 3DS crypto operations, including encryption and key generation."""

    b9_keys_set = False  # type: bool

    _b9_extdata_otp = None  # type: bytes
    _b9_extdata_keygen = None  # type: bytes
    _b9_extdata_keygen_iv = None  # type: bytes

    _otp_key = None  # type: bytes
    _otp_iv = None  # type: bytes

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

    def __init__(self, is_dev: int = 0):
        self.key_x = {}  # type: Dict[int, int]
        self.key_y = {0x03: 0xE1A00005202DDD1DBD4DC4D30AB9DC76, 0x05: 0x4D804F4E9990194613A204AC584460BE}  # type: Dict[int, int]
        self.key_normal = {}  # type: Dict[int, bytes]

        self.is_dev = is_dev

        for keyslot, keys in base_key_x.items():
            self.key_x[keyslot] = keys[is_dev]

    @property
    def b9_extdata_otp(self) -> bytes:
        if not self.b9_keys_set:
            raise KeyslotMissingError("bootrom is required to set up keys")
        return self._b9_extdata_otp

    @property
    def b9_extdata_keygen(self) -> bytes:
        if not self.b9_keys_set:
            raise KeyslotMissingError("bootrom is required to set up keys")
        return self._b9_extdata_keygen

    @property
    def b9_extdata_keygen_iv(self) -> bytes:
        if not self.b9_keys_set:
            raise KeyslotMissingError("bootrom is required to set up keys")
        return self._b9_extdata_keygen_iv

    @property
    def otp_key(self) -> bytes:
        if not self.b9_keys_set:
            raise KeyslotMissingError("bootrom is required to set up keys")
        return self._otp_key

    @property
    def otp_iv(self) -> bytes:
        if not self.b9_keys_set:
            raise KeyslotMissingError("bootrom is required to set up keys")
        return self._otp_iv

    def aes_cbc_decrypt(self, keyslot: int, iv: bytes, data: bytes) -> bytes:
        """Do AES-CBC crypto with the given keyslot and data."""
        try:
            key = self.key_normal[keyslot]
        except KeyError:
            raise KeyslotMissingError("normal key for keyslot 0x{:02x} is not set up".format(keyslot))

        cipher = AES.new(key, AES.MODE_CBC, iv)
        return cipher.decrypt(data)

    def aes_ctr(self, keyslot: int, ctr: int, data: bytes) -> bytes:
        """
        Do AES-CTR crypto with the given keyslot and data.

        Normal and DSi crypto will be automatically chosen depending on keyslot.
        """
        try:
            key = self.key_normal[keyslot]
        except KeyError:
            raise KeyslotMissingError("normal key for keyslot 0x{:02x} is not set up".format(keyslot))

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

    def set_keyslot(self, xy: str, keyslot: int, key: int):
        """Sets a keyslot to the specified key."""
        to_use = None
        if xy == 'x':
            to_use = self.key_x
        elif xy == 'y':
            to_use = self.key_y
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
        return self.common_key_y[index][self.is_dev]

    @staticmethod
    def keygen_manual(key_x: int, key_y: int) -> bytes:
        """Generate a normal key using the 3DS AES keyscrambler."""
        return rol((rol(key_x, 2, 128) ^ key_y) + 0x1FF9E9AAC5FE0408024591DC5D52768A, 87, 128).to_bytes(0x10, 'big')

    @staticmethod
    def keygen_twl_manual(key_x: int, key_y: int) -> bytes:
        """Generate a normal key using the DSi AES keyscrambler."""
        # usually would convert to LE bytes in the end then flip with [::-1], but those just cancel out
        return rol((key_x ^ key_y) + 0xFFFEFB4E295902582A680F5F1A4F3E79, 42, 128).to_bytes(0x10, 'big')

    def setup_keys_from_boot9(self, path: str = None):
        """Set up certain keys from the ARM9 bootROM."""
        if self.b9_keys_set:
            return

        if path:
            paths = (path,)
        else:
            paths = ('boot9.bin', 'boot9_prot.bin', util.config_dir + '/boot9.bin', util.config_dir + '/boot9_prot.bin')
        for p in paths:
            if isfile(p):
                keyblob_offset = 0x5860
                otp_key_offset = 0x56E0
                if self.is_dev:
                    keyblob_offset += 0x400
                    otp_key_offset += 0x20
                if getsize(p) == 0x10000:
                    keyblob_offset += 0x8000
                    otp_key_offset += 0x8000

                with open(p, 'rb') as b9:
                    b9.seek(otp_key_offset)
                    self._otp_key = b9.read(0x10)
                    self._otp_iv = b9.read(0x10)

                    b9.seek(keyblob_offset)
                    self._b9_extdata_otp = b9.read(0x24)
                    self._b9_extdata_keygen = b9.read(0x10)
                    self._b9_extdata_keygen_iv = b9.read(0x10)

                    # Original NCCH
                    b9.seek(keyblob_offset + 0x170)
                    self.key_x[0x2C] = util.readbe(b9.read(0x10))

                    # SD key
                    b9.seek(keyblob_offset + 0x190)
                    self.key_x[0x34] = util.readbe(b9.read(0x10))
                    self.key_x[0x35] = self.key_x[0x34]

                    # Common key
                    b9.seek(keyblob_offset + 0x1C0)
                    self.key_x[0x3D] = util.readbe(b9.read(0x10))

                    # NAND keys
                    b9.seek(keyblob_offset + 0x1F0)
                    self.key_y[0x04] = util.readbe(b9.read(0x10))
                    b9.seek(0x10, 1)
                    self.key_y[0x06] = util.readbe(b9.read(0x10))
                    self.key_y[0x07] = util.readbe(b9.read(0x10))

                self.b9_keys_set = True
                return

        # if keys are not set...
        raise BootromNotFoundError("not found at paths: {}".format(paths))

    def setup_keys_from_otp(self, path: str):
        """Set up console-unique keys from an OTP dump."""
        # TODO: setup_keys_from_otp
        raise NotImplementedError('setup_keys_from_otp')
