# This file is a part of ninfs.
#
# Copyright (c) 2017-2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from sys import argv, exit, path
from os.path import dirname, realpath


# noinspection PyUnresolvedReferences,PyProtectedMember
def _():
    # lazy way to get PyInstaller to detect the libraries, since this won't run at runtime
    import _gui
    import fmt_detect
    import reg_shell
    from mount import _common, cci, cdn, cia, exefs, nandctr, nandhac, nandtwl, ncch, romfs, sd, srl, threedsx, titledir
    from pyctr.types import crypto, exefs, ncch, romfs, smdh, tmd, util


path.insert(0, dirname(realpath(__file__)))

if len(argv) < 2 or argv[1] in {'gui', 'gui_i_want_to_be_an_admin_pls'}:
    from _gui import main
    admin = False
    if len(argv) > 1:
        admin = argv.pop(1) == 'gui_i_want_to_be_an_admin_pls'
    exit(main(_pyi=True, _allow_admin=admin))
else:
    from main import mount
    exit(mount(argv.pop(1).lower()))
