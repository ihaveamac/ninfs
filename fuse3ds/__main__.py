from os.path import dirname, realpath
from sys import argv, exit, path

# path fun times
path.insert(0, dirname(realpath(__file__)))
from main import exit_print_types, mount

if len(argv) < 2:
    exit_print_types()

exit(mount(argv.pop(1).lower()))
