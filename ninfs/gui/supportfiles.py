# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from contextlib import suppress
from os import environ
from os.path import isfile, join

from pyctr.util import config_dirs

b9_paths = []
seeddb_paths = []
for p in config_dirs:
    b9_paths.append(join(p, 'boot9.bin'))
    b9_paths.append(join(p, 'boot9_prot.bin'))
    seeddb_paths.append(join(p, 'seeddb.bin'))

with suppress(KeyError):
    b9_paths.insert(0, environ['BOOT9_PATH'])

with suppress(KeyError):
    seeddb_paths.insert(0, environ['SEEDDB_PATH'])

last_b9_file = ''
last_seeddb_file = ''

for p in b9_paths:
    if isfile(p):
        last_b9_file = p
        break

for p in seeddb_paths:
    if isfile(p):
        last_seeddb_file = p
        break
