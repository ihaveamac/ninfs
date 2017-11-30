from collections import namedtuple
from io import BytesIO

from . import util

IVFC_HEADER_SIZE = 0x5C
IVFC_ROMFS_MAGIC_NUM = 0x10000
ROMFS_LV3_HEADER_SIZE = 0x28


class RomFSException(Exception):
    """Generic exception for RomFS operations."""


class InvalidIVFCException(RomFSException):
    """Invalid IVFC header exception."""


class InvalidRomFSHeaderException(RomFSException):
    """Invalid RomFS Level 3 header."""


class RomFSFileNotFoundException(RomFSException):
    """Invalid file path in RomFS Level 3."""


class RomFSFileIndexNotSetup(RomFSException):
    """RomFS file index still needs to be set up."""


RomFSRegion = namedtuple('RomFSRegion', 'offset size')
RomFSDirectoryEntry = namedtuple('RomFSDirectoryEntry', 'type contents')
RomFSFileEntry = namedtuple('RomFSFileEntry', 'type offset size')


class RomFSReader:
    _root = {}

    """Class for 3DS RomFS Level 3 partition."""
    def __init__(self, *, dirmeta: dict, filemeta: dict, filedata_offset: int):
        self._dirmeta_offset = dirmeta['offset']
        self._dirmeta_size = dirmeta['size']
        self._filemeta_offset = filemeta['offset']
        self._filemeta_size = filemeta['size']
        self._filedata_offset = filedata_offset

    def get_dirmeta_region(self):
        return RomFSRegion(offset=self._dirmeta_offset, size=self._dirmeta_size)

    def get_filemeta_region(self):
        return RomFSRegion(offset=self._filemeta_offset, size=self._filemeta_size)

    def get_filedata_offset(self):
        return self._filedata_offset

    def get_info_from_path(self, path):
        curr = self._root
        if path[0] == '/':
            path = path[1:]
        for part in path.split('/'):
            if part == '':
                break
            try:
                curr = curr['contents'][part]
            except KeyError:
                raise RomFSFileNotFoundException(path)
        if curr['type'] == 'dir':
            return RomFSDirectoryEntry(type='dir', contents=(*curr['contents'].keys(),))
        elif curr['type'] == 'file':
            return RomFSFileEntry(type='file', offset=curr['offset'], size=curr['size'])

    @staticmethod
    def validate_lv3_header(length: int, dirhash: dict, dirmeta: dict, filehash: dict, filemeta: dict,
                            filedata_offset: int):
        if length != ROMFS_LV3_HEADER_SIZE:
            raise InvalidRomFSHeaderException("Length in RomFS Lv3 header is not 0x28")
        if dirhash['offset'] < length:
            raise InvalidRomFSHeaderException("Directory Hash offset is before the end of the Lv3 header")
        if dirmeta['offset'] < dirhash['offset'] + dirhash['size']:
            raise InvalidRomFSHeaderException("Directory Metadata offset is before the end of the Directory Hash "
                                              "region")
        if filehash['offset'] < dirmeta['offset'] + dirmeta['size']:
            raise InvalidRomFSHeaderException("File Hash offset is before the end of the Directory Metadata region")
        if filemeta['offset'] < filehash['offset'] + filehash['size']:
            raise InvalidRomFSHeaderException("File Metadata offset is before the end of the File Hash region")
        if filedata_offset < filemeta['offset'] + filemeta['size']:
            raise InvalidRomFSHeaderException("File Data offset is before the end of the File Metadata region")

    @classmethod
    def from_lv3_header(cls, header: bytes):
        header_length = len(header)
        if header_length < ROMFS_LV3_HEADER_SIZE:
            raise InvalidRomFSHeaderException("RomFS Lv3 given header length is too short "
                                              "(0x{:X} instead of 0x{:X})".format(header_length, ROMFS_LV3_HEADER_SIZE))

        lv3_header_length = util.readle(header[0x0:0x4])
        lv3_dirhash = {'offset': util.readle(header[0x4:0x8]), 'size': util.readle(header[0x8:0xC])}
        lv3_dirmeta = {'offset': util.readle(header[0xC:0x10]), 'size': util.readle(header[0x10:0x14])}
        lv3_filehash = {'offset': util.readle(header[0x14:0x18]), 'size': util.readle(header[0x18:0x1C])}
        lv3_filemeta = {'offset': util.readle(header[0x1C:0x20]), 'size': util.readle(header[0x20:0x24])}
        lv3_filedata_offset = util.readle(header[0x24:0x28])

        cls.validate_lv3_header(lv3_header_length, lv3_dirhash, lv3_dirmeta, lv3_filehash, lv3_filemeta,
                                lv3_filedata_offset)

        return cls(dirmeta=lv3_dirmeta, filemeta=lv3_filemeta, filedata_offset=lv3_filedata_offset)

    def parse_metadata(self, raw_dirmeta: bytes, raw_filemeta: bytes):
        dirmeta_io = BytesIO(raw_dirmeta)
        filemeta_io = BytesIO(raw_filemeta)

        # maybe this should be switched to BytesIO
        def iterate_dir(out: dict, raw: bytes):
            first_child_dir = util.readle(raw[0x8:0xC])
            first_file = util.readle(raw[0xC:0x10])

            out['type'] = 'dir'
            out['contents'] = {}

            # iterate through all child directories
            if first_child_dir != 0xFFFFFFFF:
                dirmeta_io.seek(first_child_dir)
                while True:
                    child_dir_meta = dirmeta_io.read(0x18)
                    next_sibling_dir = util.readle(child_dir_meta[0x4:0x8])
                    child_dir_filename = dirmeta_io.read(util.readle(child_dir_meta[0x14:0x18]))
                    child_dir_filename = child_dir_filename.decode('utf-16le')
                    out['contents'][child_dir_filename] = {}

                    iterate_dir(out['contents'][child_dir_filename], child_dir_meta)
                    if next_sibling_dir == 0xFFFFFFFF:
                        break
                    dirmeta_io.seek(next_sibling_dir)

            if first_file != 0xFFFFFFFF:
                filemeta_io.seek(first_file)
                while True:
                    child_file_meta = filemeta_io.read(0x20)
                    next_sibling_file = util.readle(child_file_meta[0x4:0x8])
                    child_file_offset = util.readle(child_file_meta[0x8:0x10])
                    child_file_size = util.readle(child_file_meta[0x10:0x18])
                    child_file_filename = filemeta_io.read(util.readle(child_file_meta[0x1C:0x20])).decode('utf-16le')
                    out['contents'][child_file_filename] = {'type': 'file', 'offset': child_file_offset,
                                                            'size': child_file_size}

                    if next_sibling_file == 0xFFFFFFFF:
                        break
                    filemeta_io.seek(next_sibling_file)

        root_meta = dirmeta_io.read(0x18)
        iterate_dir(self._root, root_meta)

        dirmeta_io.close()
        filemeta_io.close()


def get_lv3_offset_from_ivfc(header: bytes) -> int:
    """
    Parse the IVFC header to get the offset of the Level 3 RomFS. Offset isrelative to the beginning of the header.

    This currently only generates the required offsets to get the Lv3 partition offset, not any others.
    """
    header_length = len(header)
    header_magic = header[0x0:0x4]
    header_magic_num = util.readle(header[0x4:0x8])

    if header_magic != b'IVFC':
        raise InvalidIVFCException("IVFC magic not found in given header")
    if header_magic_num != IVFC_ROMFS_MAGIC_NUM:
        raise InvalidIVFCException("IVFC Magic number is invalid "
                                   "(0x{:X} instead of 0x{:X})".format(header_magic_num, IVFC_ROMFS_MAGIC_NUM))
    if header_length < 0x5C:
        raise InvalidIVFCException("IVFC given header length is too short "
                                   "(0x{:X} instead of 0x{:X})".format(header_length, IVFC_HEADER_SIZE))

    master_hash_size = util.readle(header[0x8:0xC])
    lv3_block_size = util.readle(header[0x4C:0x50])
    lv3_hash_block_size = 1 << lv3_block_size
    lv3_offset = util.roundup(0x60 + master_hash_size, lv3_hash_block_size)
    return lv3_offset
