# -*- mode: python ; coding: utf-8 -*-

import sys

block_cipher = None


a = Analysis(['ninfs/_pyi_main.py'],
             pathex=['ninfs'],
             binaries=[],
             datas=[],
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
    exe = EXE(pyz,
              a.scripts,
              a.binaries,
              a.zipfiles,
              a.datas,
              [],
              name='ninfs',
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
                     'LSMinimumSystemVersion': '10.12.0',
                     'NSHighResolutionCapable': True,
                     'CFBundleShortVersionString': '2.0',
                     'CFBundleVersion': '2.0',
                 })
