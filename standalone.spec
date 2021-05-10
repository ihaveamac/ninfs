# -*- mode: python ; coding: utf-8 -*-

import sys
import os

# to import mountinfo
sys.path.insert(0, os.getcwd())

from ninfs import mountinfo

mount_module_paths = [f'mount.{x}' for x in mountinfo.types.keys()]

imports = [
    'certifi',
    'gui',
    'mountinfo',
    'mount',
    'main',
    'reg_shell',
    'fmt_detect',
    'fuse',
] + mount_module_paths


a = Analysis(['ninfs/_frozen_main.py'],
             pathex=['./ninfs'],
             binaries=[],
             datas=[('ninfs/gui/data', 'guidata')],
             hiddenimports=imports,
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=None,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=None)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='ninfs',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False)
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
             bundle_identifier='net.ihaveahax.ninfs',
             info_plist={
                 'LSMinimumSystemVersion': '10.12.6',
                 #'NSRequiresAquaSystemAppearance': True,
                 'NSHighResolutionCapable': True,
                 'CFBundleShortVersionString': '2.0b4',
                 'CFBundleVersion': '2000',
             }
            )
