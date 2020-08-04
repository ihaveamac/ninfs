# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from sys import exit
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List

try:
    # noinspection PyProtectedMember
    from ._crypto import XTSN
except ImportError:
    try:
        from _crypto import XTSN
    except ImportError:
        exit("Couldn't load ccrypto. The extension needs to be compiled.")


def parse_biskeydump(keys: str):
    bis_keys: List[List[bytes]] = [[None, None], [None, None], [None, None], [None, None]]
    for l in keys.splitlines():
        # old format
        if l.startswith('BIS KEY'):
            data = l.split()[2:]
            key_idx = int(data[0])
            key_type = data[1][1:-2]
            if key_type not in {'crypt', 'tweak'}:
                raise RuntimeError('unknown type')  # TODO: give this a special error
            bis_keys[key_idx][0 if key_type == 'crypt' else 1] = bytes.fromhex(data[2])
        # new format
        elif l.startswith('bis_key'):
            keyinfo, key = l.split(" = ")
            try:
                key_idx = int(keyinfo.split("_")[2])
            except ValueError:
                continue  # some lines such as "bis_key_source_XX" may cause this exception
            bis_keys[key_idx][0] = bytes.fromhex(key[:32])
            bis_keys[key_idx][1] = bytes.fromhex(key[32:])
    return bis_keys
