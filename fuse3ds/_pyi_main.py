from typing import TYPE_CHECKING
from sys import argv, exit, path, executable
from os.path import dirname, realpath

if TYPE_CHECKING:
    # lazy way to get PyInstaller to detect the libraries, since this won't run at runtime
    import _gui
    import fmt_detect
    import reg_shell
    # noinspection PyProtectedMember
    from mount import _common, cci, cdn, cia, exefs, nand, ncch, romfs, sd, titledir
    from pyctr.types import crypto, exefs, ncch, romfs, smdh, tmd, util

path.append(dirname(realpath(__file__)))

if len(argv) < 2 or argv[1] in {'gui', 'gui_i_want_to_be_an_admin_pls'}:
    from _gui import main
    print('Starting the GUI!')
    import _gui
    admin = False
    if len(argv) > 1:
        admin = argv[1] == 'gui_i_want_to_be_an_admin_pls'
        del argv[1]
    exit(main(_pyi=True, _allow_admin=admin))
else:
    from main import mount
    exit(mount(argv.pop(1).lower()))
