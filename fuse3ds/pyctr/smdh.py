from types import MappingProxyType
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from typing import BinaryIO, Dict, Tuple

SMDH_SIZE = 0x36C0

region_names = (
    'Japanese',
    'English',
    'French',
    'German',
    'Italian',
    'Spanish',
    'Simplified Chinese',
    'Korean',
    'Dutch',
    'Portuguese',
    'Russian',
    'Traditional Chinese',
)

AppTitle = NamedTuple('AppTitle', (('short_desc', str), ('long_desc', str), ('publisher', str)))


class SMDHError(Exception):
    """Generic exception for SMDH operations."""


class InvalidSMDHError(Exception):
    """Invalid SMDH contents."""


class SMDH:
    """
    Class for 3DS SMDH. Icon data is currently not supported.

    https://www.3dbrew.org/wiki/SMDH
    """

    # TODO: support other settings

    def __init__(self, names: 'Dict[str, AppTitle]'):
        self.names = MappingProxyType({n: names.get(n, None) for n in region_names})  # type: Dict[str, AppTitle]

    @classmethod
    def load(cls, fp: 'BinaryIO') -> 'SMDH':
        """Load an SMDH from a file-like object."""
        smdh = fp.read(SMDH_SIZE)
        if len(smdh) != SMDH_SIZE:
            raise InvalidSMDHError('invalid size (expected: {:#6x}, got: {:#6x}'.format(SMDH_SIZE, len(smdh)))
        if smdh[0:4] != b'SMDH':
            raise InvalidSMDHError('SMDH magic not found')

        app_structs = smdh[8:0x2008]
        names = {}  # type: Dict[str, AppTitle]
        # due to region_names only being 12 elements, this will only process 12. the other 4 are unused.
        for app_title, region in zip((app_structs[x:x + 0x200] for x in range(0, 0x200, 0x2000)), region_names):
            names[region] = AppTitle(app_title[0:0x80].decode('utf-16le').strip('\0'),
                                     app_title[0x80:0x180].decode('utf-16le').strip('\0'),
                                     app_title[0x180:0x200].decode('utf-16le').strip('\0'))
        return cls(names)

    @classmethod
    def from_file(cls, fn: str) -> 'SMDH':
        with open(fn, 'rb') as f:
            return cls.load(f)
