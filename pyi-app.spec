# -*- mode: python ; coding: utf-8 -*-

import sys

# based on https://github.com/Legrandin/pycryptodome/blob/b3a394d0837ff92919d35d01de9952b8809e802d/setup.py
with open('ninfs/__init__.py', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('__version__'):
            version = eval(line.split('=')[1])

block_cipher = None

datas = []
if sys.platform == 'win32':
    datas.append(['ninfs/data', 'data'])


a = Analysis(['ninfs/_pyi_main.py'],
             pathex=['ninfs'],
             binaries=[],
             datas=datas,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

# build exe for Windows
if sys.platform == 'win32':
    from platform import architecture
    name = f'ninfs-{"x86" if architecture()[0] == "32bit" else "x64"}'
    exe = EXE(pyz,
              a.scripts,
              a.binaries,
              a.zipfiles,
              a.datas,
              [],
              name=name,
              debug=False,
              bootloader_ignore_signals=False,
              strip=False,
              upx=True,
              upx_exclude=[],
              runtime_tmpdir=None,
              console=True, icon='ninfs\\data\\windows.ico')

# build app for macOS
elif sys.platform == 'darwin':
    exe = EXE(pyz,
              a.scripts,
              [],
              exclude_binaries=True,
              name='ninfs',
              debug=False,
              bootloader_ignore_signals=False,
              strip=False,
              upx=True,
              console=False, icon='build/AppIcon.icns')

    coll = COLLECT(exe,
                   a.binaries,
                   a.zipfiles,
                   a.datas,
                   strip=False,
                   upx=True,
                   upx_exclude=[],
                   name='ninfs')

    app = BUNDLE(coll,
                 name='ninfs.app',
                 icon='build/AppIcon.icns',
                 bundle_identifier='net.ianburgwin.ninfs',
                 info_plist={
                     # Qt only supports the 3 latest macOS versions, like Apple does with security updates.
                     'LSMinimumSystemVersion': '10.13.0',
                     'NSHighResolutionCapable': True,
                     'CFBundleShortVersionString': version,
                     'CFBundleVersion': version,
                 })
