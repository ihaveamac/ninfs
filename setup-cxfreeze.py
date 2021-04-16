import sys

from cx_Freeze import setup, Executable

from ninfs import mountinfo

mount_module_paths = [f'ninfs.mount.{x}' for x in mountinfo.types.keys()]

build_exe_options = {
    'includes': [
        'ninfs',
        'ninfs.gui',
        'ninfs.mountinfo',
        'ninfs.main',
        'ninfs.reg_shell',
        'ninfs.fmt_detect',
        'ninfs.fuse',
    ] + mount_module_paths,
}

build_msi_options = {
    'upgrade_code': '{4BC1D604-0C12-428A-AA22-7BB673EC8266}',
    'install_icon': 'ninfs/gui/data/windows.ico'
}

executables = [
    Executable('ninfs/_frozen_main.py',
               target_name='ninfs',
               icon='ninfs/gui/data/windows.ico')
]

if sys.platform == 'win32':
    executables.append(Executable('ninfs/_frozen_main.py',
                                  base='Win32GUI',
                                  target_name='ninfsw',
                                  icon='ninfs/gui/data/windows.ico'))

    executables.append(Executable('ninfs/winpathmodify.py',
                                  target_name='winpathmodify'))

# based on https://github.com/Legrandin/pycryptodome/blob/b3a394d0837ff92919d35d01de9952b8809e802d/setup.py
with open('ninfs/__init__.py', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('__version__'):
            version = eval(line.split('=')[1])

setup(
    name='ninfs',
    version=version,
    description='FUSE filesystem Python scripts for Nintendo console files',
    options={'build_exe': build_exe_options},
    executables=executables
)
