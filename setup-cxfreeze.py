import sys
from cx_Freeze import setup, Executable
from distutils.core import Extension

build_exe_options = {
    'includes': [
        'ninfs',
        'ninfs.gui',
        'ninfs.hac.crypto',
        'ninfs.mount.cci',
        'ninfs.mount.cdn',
        'ninfs.mount.cia',
        'ninfs.mount.exefs',
        'ninfs.mount.nandctr',
        'ninfs.mount.nandhac',
        'ninfs.mount.nandtwl',
        'ninfs.mount.ncch',
        'ninfs.mount.romfs',
        'ninfs.mount.sd',
        'ninfs.mount.srl',
        'ninfs.mount.threedsx',
        'ninfs.main',
        'ninfs.reg_shell',
        'ninfs.fmt_detect',
        'ninfs.fuse',
        'pyctr.type.cci',
        'pyctr.type.cdn',
        'pyctr.type.cia',
        'pyctr.type.exefs',
        'pyctr.type.ncch',
        'pyctr.type.romfs',
        'pyctr.type.sd',
        'pyctr.type.smdh',
        'pyctr.type.tmd',
    ],
}

build_msi_options = {
    'upgrade_code': '{4BC1D604-0C12-428A-AA22-7BB673EC8266}',
    'install_icon': 'ninfs/gui/data/windows.ico'
}

base = None
if sys.platform == 'win32':
    base = 'Win32GUI'

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
    executables=[Executable('ninfs/_frozen_main.py', base=base, targetName='ninfs', icon='ninfs/gui/data/windows.ico',
                            shortcutDir='ninfs', shortcutName='ninfs')],
    ext_modules=[Extension('ninfs.hac._crypto', sources=['ninfs/hac/_crypto.cpp', 'ninfs/hac/aes.cpp'],
                           extra_compile_args=['/Ox' if sys.platform == 'win32' else '-O3',
                                               '' if sys.platform == 'win32' else '-std=c++11'])]
)
