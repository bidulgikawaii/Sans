# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('shapely')


a = Analysis(
    ['C:\\Users\\orior\\OneDrive\\Documents\\Sans\\TheTest.py'],
    pathex=['C:\\Users\\orior\\OneDrive\\Documents\\Sans'],
    binaries=[],
    datas=[('C:\\Users\\orior\\OneDrive\\Documents\\Sans\\Image', 'Image'), ('C:\\Users\\orior\\OneDrive\\Documents\\Sans\\Font', 'Font'), ('C:\\Users\\orior\\OneDrive\\Documents\\Sans\\Sound', 'Sound')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SansClient',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SansClient',
)
