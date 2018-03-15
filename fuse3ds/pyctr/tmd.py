from hashlib import sha256
from typing import BinaryIO, NamedTuple, Iterable

from .util import readbe

__all__ = ['CHUNK_RECORD_SIZE', 'TitleMetadataError', 'InvalidSignatureTypeError', 'InvalidHashError',
           'ContentInfoRecord', 'ContentChunkRecord', 'ContentTypeFlags', 'TitleVersion', 'TitleMetadataReader']

CHUNK_RECORD_SIZE = 0x30

signature_types = {
    # RSA_4096 SHA1 (unused on 3DS)
    0x00010000: (0x200, 0x3C),
    # RSA_2048 SHA1 (unused on 3DS)
    0x00010001: (0x100, 0x3C),
    # Elliptic Curve with SHA1 (unused on 3DS)
    0x00010002: (0x3C, 0x40),
    # RSA_4096 SHA256
    0x00010003: (0x200, 0x3C),
    # RSA_2048 SHA256
    0x00010004: (0x100, 0x3C),
    # ECDSA with SHA256
    0x00010005: (0x3C, 0x40),
}


class TitleMetadataError(Exception):
    """Generic exception for TitleMetadata operations."""


class InvalidSignatureTypeError(TitleMetadataError):
    """Invalid signature type was used."""


class InvalidHashError(TitleMetadataError):
    """Hash mismatch in the Title Metadata."""


# apparently typing.NamedTuple being subclassed this way does not properly support type hints in PyCharm...
# maybe I should stop supporting 3.5
class ContentTypeFlags(NamedTuple('_ContentTypeFlags',
                       (('encrypted', bool), ('disc', bool), ('cfm', bool), ('optional', bool), ('shared', bool)))):
    __slots__ = ()
    def __index__(self) -> int:
        return self.encrypted | (self.disc << 1) | (self.cfm << 2) | (self.optional << 14) | (self.shared << 15)

    __int__ = __index__

    def __format__(self, format_spec: str) -> str:
        return self.__int__().__format__(format_spec)

    @classmethod
    def from_int(cls, flags: int) -> 'ContentTypeFlags':
        # PyCharm's inspector is wrong here, cls returns ContentTypeFlags.
        # noinspection PyTypeChecker
        return cls(bool(flags & 1), bool(flags & 2), bool(flags & 4), bool(flags & 0x4000), bool(flags & 0x8000))


class ContentInfoRecord(NamedTuple('_ContentInfoRecord',
                                   (('index_offset', int), ('command_count', int), ('hash', bytes)))):
    __slots__ = ()
    def __bytes__(self) -> bytes:
        return b''.join((self.index_offset.to_bytes(2, 'big'), self.command_count.to_bytes(2, 'big'), self.hash))


class ContentChunkRecord(NamedTuple('_ContentChunkRecord',
                                    (('id', str), ('cindex', int), ('type', ContentTypeFlags), ('size', int),
                                     ('hash', bytes)))):
    __slots__ = ()
    def __bytes__(self) -> bytes:
        return b''.join((bytes.fromhex(self.id), self.cindex.to_bytes(2, 'big'), self.type.to_bytes(2, 'big'),
                         self.size.to_bytes(8, 'big'), self.hash))


class TitleVersion(NamedTuple('_TitleVersion', (('major', int), ('minor', int), ('micro', int)))):
    __slots__ = ()
    def __str__(self) -> str:
        return '{0.major}.{0.minor}.{0.micro}'.format(self)

    def __index__(self) -> int:
        return (self.major << 10) | (self.minor << 4) | self.micro

    __int__ = __index__

    def __format__(self, format_spec: str) -> str:
        return self.__int__().__format__(format_spec)

    @classmethod
    def from_int(cls, ver: int) -> 'TitleVersion':
        # PyCharm's inspector is wrong here, cls returns TitleVersion.
        # noinspection PyTypeChecker
        return cls((ver >> 10) & 0x3F, (ver >> 4) & 0x3F, ver & 0xF)


class TitleMetadataReader:
    """Class for 3DS Title Metadata."""

    __slots__ = ('title_id', 'save_size', 'srl_save_size', 'title_version', 'info_records',
                 'chunk_records', 'content_count')

    def __init__(self, *, title_id: str, save_size: int, srl_save_size: int, title_version: TitleVersion,
                 info_records: Iterable[ContentInfoRecord], chunk_records: Iterable[ContentChunkRecord]):
        self.title_id = title_id
        self.save_size = save_size
        self.srl_save_size = srl_save_size
        self.title_version = title_version
        self.info_records = tuple(info_records)
        self.chunk_records = tuple(chunk_records)
        self.content_count = len(self.chunk_records)

    def __hash__(self) -> int:
        return hash((self.title_id, self.save_size, self.srl_save_size, self.title_version,
                     self.info_records, self.chunk_records))

    def __repr__(self) -> str:
        return '<TitleMetadataReader title_id={0.title_id!r} title_version={0.title_version!r} ' \
               'content_count={0.content_count!r}>'.format(self)

    @classmethod
    def load(cls, fp: BinaryIO, verify_hashes: bool = True) -> 'TitleMetadataReader':
        """Load a tmd from a file-like object."""
        sig_type = readbe(fp.read(4))
        try:
            sig_size, sig_padding = signature_types[sig_type]
        except KeyError:
            raise InvalidSignatureTypeError("{:08X}".format(sig_type))

        # I may load the signature if I decide to have a function that returns the tmd in the original format.
        if fp.seekable():
            fp.seek(sig_size + sig_padding, 1)
        else:
            fp.read(sig_size + sig_padding)

        header = fp.read(0xC4)

        # only values that actually have a use are loaded here.
        # several fields in were left in from the Wii tmd and have no function on 3DS.
        # I may load the extra values if I decide to have a function that returns the tmd in the original format.
        title_id = header[0x4C:0x54].hex()
        save_size = readbe(header[0x5A:0x5E])
        srl_save_size = readbe(header[0x5E:0x62])
        title_version = TitleVersion.from_int(readbe(header[0x9C:0x9E]))
        content_count = readbe(header[0x9E:0xA0])

        content_info_records_hash = header[0xA4:0xC4]

        content_info_records_raw = fp.read(0x900)
        if verify_hashes:
            real_hash = sha256(content_info_records_raw)
            if content_info_records_hash != real_hash.digest():
                raise InvalidHashError("Content Info Records hash is invalid")

        # the hashes of this is sort of based on assumption. I need to figure out how hashes in the info records
        #   work more. of course, in practice, not more than one info record is used, so this is not urgent.
        info_records = []
        for ir in (content_info_records_raw[i:i + 0x24] for i in range(0, 0x900, 0x24)):
            if ir != b'\0' * 0x24:
                info_records.append(ContentInfoRecord(index_offset=readbe(ir[0:2]),
                                                      command_count=readbe(ir[2:4]),
                                                      hash=ir[4:36]))

        content_chunk_records_raw = fp.read(content_count * CHUNK_RECORD_SIZE)
        # TODO: verify hashes of chunk_records (needs more testing)

        chunk_records = []
        for cr in (content_chunk_records_raw[i:i + CHUNK_RECORD_SIZE] for i in
                   range(0, content_count * CHUNK_RECORD_SIZE, CHUNK_RECORD_SIZE)):
            chunk_records.append(ContentChunkRecord(id=cr[0:4].hex(),
                                                    cindex=readbe(cr[4:6]),
                                                    type=ContentTypeFlags.from_int(readbe(cr[6:8])),
                                                    size=readbe(cr[8:16]),
                                                    hash=cr[16:48]))

        return cls(title_id=title_id, save_size=save_size, srl_save_size=srl_save_size, title_version=title_version,
                   info_records=info_records, chunk_records=chunk_records)

    @classmethod
    def from_file(cls, fn: str, *, verify_hashes: bool = True) -> 'TitleMetadataReader':
        with open(fn, 'rb') as f:
            return cls.load(f, verify_hashes=verify_hashes)
