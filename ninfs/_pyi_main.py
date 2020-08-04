# This file is a part of ninfs.
#
# Copyright (c) 2017-2020 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from sys import argv, exit, path
from os.path import dirname, realpath


# noinspection PyUnresolvedReferences,PyProtectedMember
def _():
    # lazy way to get PyInstaller to detect the libraries, since this won't run at runtime
    import fmt_detect
    import reg_shell
    from mount import _common, cci, cdn, cia, exefs, nandctr, nandhac, nandtwl, ncch, romfs, sd, srl, threedsx, titledir
    from pyctr.type import crypto, exefs, ncch, romfs, smdh, tmd, util


path.insert(0, dirname(realpath(__file__)))

if len(argv) < 2 or argv[1] in {'gui', 'gui_i_want_to_be_an_admin_pls'}:
    print('The GUI is currently not available.')
else:
    from main import mount
    exit(mount(argv.pop(1).lower()))
