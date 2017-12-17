from collections import namedtuple
from hashlib import sha256
from os.path import isfile
from typing import BinaryIO

from . import crypto, util


class NCCHException(Exception):
    """Generic exception for NCCH operations."""


class InvalidNCCHException(NCCHException):
    """Invalid NCCH header exception."""


class NCCHSeedException(NCCHException):
    """NCCH seed is not set up, or attempted to set up seed when seed crypto is not used."""


def check_seeddb_file(path=None):
    """Check for seeddb.bin."""
    if path:
        paths = (path,)
    else:
        paths = ('seeddb.bin', util.config_dir + '/seeddb.bin')
    for fn in paths:
        if isfile(fn):
            return fn
    return False


def get_seed(f: BinaryIO, program_id: int):
    """Get a seed in a seeddb.bin from an I/O stream."""
    tid_bytes = program_id.to_bytes(0x8, 'little')
    f.seek(0)
    seed_count = util.readle(f.read(2))
    f.seek(0x10)
    for _ in range(seed_count):
        entry = f.read(0x20)
        if entry[0:8] == tid_bytes:
            return entry[0x8:0x18]
    raise NCCHSeedException("missing seed for {:016X} from seeddb.bin".format(program_id))


NCCH_MEDIA_UNIT = 0x200
extra_cryptoflags = {0x00: 0x2C, 0x01: 0x25, 0x0A: 0x18, 0x0B: 0x1B}

fixed_system_key = 0x527CE630A9CA305F3696F3CDE954194B

NCCHRegion = namedtuple('NCCHRegion', 'offset size')
NCCHFlags = namedtuple('NCCHFlags', 'crypto_method executable fixed_crypto_key no_romfs no_crypto uses_seed')


class NCCHReader:
    """Class for 3DS NCCH container."""

    seed_set_up = False
    _seeded_key_y = None

    def __init__(self, *, key_y: bytes, content_size: int, partition_id: int, seed_verify: bytes, program_id: int,
                 product_code: str, extheader_size: int, flags: NCCHFlags, plain_region: NCCHRegion,
                 logo_region: NCCHRegion, exefs_region: NCCHRegion, romfs_region: NCCHRegion):
        self._key_y = key_y
        self.content_size = content_size
        self.partition_id = partition_id
        self._seed_verify = seed_verify
        self.program_id = program_id
        self.product_code = product_code
        self._extheader_size = extheader_size
        self.flags = flags
        self.plain_region = plain_region
        self.logo_region = logo_region
        self.exefs_region = exefs_region
        self.romfs_region = romfs_region

    def get_key_y(self, original: bool = False) -> bytes:
        if original or not self.flags.uses_seed:
            return self._key_y
        if self.flags.uses_seed and not self.seed_set_up:
            raise NCCHSeedException("NCCH uses seed crypto, but seed is not set up")
        else:
            return self._seeded_key_y

    @property
    def extra_keyslot(self) -> int:
        return extra_cryptoflags[self.flags.crypto_method]

    def check_for_extheader(self) -> bool:
        return bool(self._extheader_size)

    def setup_seed(self, seed: bytes):
        if not self.flags.uses_seed:
            raise NCCHSeedException("NCCH does not use seed crypto")
        seed_verify_hash = sha256(seed + self.program_id.to_bytes(0x8, 'little')).digest()
        if seed_verify_hash[0x0:0x4] != self._seed_verify:
            raise NCCHSeedException("given seed does not match with seed verify hash in header")
        self._seeded_key_y = sha256(self._key_y + seed).digest()[0:16]
        self.seed_set_up = True

    @classmethod
    def from_header(cls, header: bytes) -> 'NCCHReader':
        """Create an NCCHReader from an NCCH header."""
        header_len = len(header)

        if header_len != 0x200:
            raise InvalidNCCHException("given NCCH header is not 0x200")
        if header[0x100:0x104] != b'NCCH':
            raise InvalidNCCHException("NCCH magic not found in given header")

        key_y = header[0x0:0x10]
        content_size = util.readle(header[0x104:0x108]) * NCCH_MEDIA_UNIT
        partition_id = util.readle(header[0x108:0x110])
        seed_verify = header[0x114:0x118]
        product_code = header[0x150:0x160].decode('ascii').strip('\0')
        program_id = util.readle(header[0x118:0x120])
        extheader_size = util.readle(header[0x180:0x184])
        flags_raw = header[0x188:0x190]
        plain_region = NCCHRegion(offset=util.readle(header[0x190:0x194]) * NCCH_MEDIA_UNIT,
                                  size=util.readle(header[0x194:0x198]) * NCCH_MEDIA_UNIT)
        logo_region = NCCHRegion(offset=util.readle(header[0x198:0x19C]) * NCCH_MEDIA_UNIT,
                                 size=util.readle(header[0x19C:0x1A0]) * NCCH_MEDIA_UNIT)
        exefs_region = NCCHRegion(offset=util.readle(header[0x1A0:0x1A4]) * NCCH_MEDIA_UNIT,
                                  size=util.readle(header[0x1A4:0x1A8]) * NCCH_MEDIA_UNIT)
        romfs_region = NCCHRegion(offset=util.readle(header[0x1B0:0x1B4]) * NCCH_MEDIA_UNIT,
                                  size=util.readle(header[0x1B4:0x1B8]) * NCCH_MEDIA_UNIT)

        flags = NCCHFlags(crypto_method=flags_raw[3], executable=bool(flags_raw[5] & 0x2),
                          fixed_crypto_key=bool(flags_raw[7] & 0x1), no_romfs=bool(flags_raw[7] & 0x2),
                          no_crypto=bool(flags_raw[7] & 0x4), uses_seed=bool(flags_raw[7] & 0x20))

        return cls(key_y=key_y, content_size=content_size, partition_id=partition_id, seed_verify=seed_verify,
                   program_id=program_id, product_code=product_code, extheader_size=extheader_size, flags=flags,
                   plain_region=plain_region, logo_region=logo_region, exefs_region=exefs_region,
                   romfs_region=romfs_region)
