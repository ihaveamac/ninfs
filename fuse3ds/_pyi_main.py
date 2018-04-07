from sys import argv, exit, path, executable
from os.path import dirname, realpath

path.append(dirname(realpath(__file__)))

if len(argv) < 2 or argv[1] in {'gui', 'gui_i_want_to_be_an_admin_pls'}:
    from _gui import main
    print('Starting the GUI!')
    import _gui
    admin = False
    if len(argv) > 1:
        admin = argv[1] == 'gui_i_want_to_be_an_admin_pls'
        del argv[1]
    exit(main(_pyi=True))
else:
    from main import mount
    exit(mount(argv.pop(1).lower()))
