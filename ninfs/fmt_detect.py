# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional


def detect_format(header: bytes) -> 'Optional[str]':
    """Attempt to detect the format of a file format based on the 0x200 header."""
    if len(header) not in {0x200, 0x400}:
        raise RuntimeError('given header is not 0x200 or 0x400 bytes')

    magic_0x100 = header[0x100:0x104]
    if magic_0x100 == b'NCCH':
        return 'ncch'

    elif magic_0x100 == b'NCSD':
        if header[0x108:0x110] == b'\0' * 8:
            return 'nandctr'
        else:
            return 'cci'

    elif header[0:4] == b'IVFC' or header[0:4] == bytes.fromhex('28000000'):
        # IVFC magic, or hardcoded romfs header size
        return 'romfs'

    elif header[0:0x10] == bytes.fromhex('20200000 00000000 000A0000 50030000'):
        # hardcoded header, type, version, cert chain, ticket sizes (should never change in practice)
        return 'cia'

    elif header[0xC0:0xC8] == bytes.fromhex('24FFAE51 699AA221'):
        return 'srl'

    elif header[0:4] == b'3DSX':
        return 'threedsx'

    # Not entirely sure if this is always the same.
    # https://dsibrew.org/wiki/Bootloader#Stage_2
    elif header[0x220:0x240] == bytes.fromhex('00080000 10640200 00807B03 00660200 '
                                              '006E0200 88750200 00807B03 00760200'):
        return 'nandtwl'

    # exefs is last because it's the hardest to do
    # this should work with any official files
    for offs in range(0, 0xA0, 0x10):
        try:
            header[offs:offs + 8].decode('ascii')
        except UnicodeDecodeError:
            return None
    # if decoding all of them worked...
    return 'exefs'
