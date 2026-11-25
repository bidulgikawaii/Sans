# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:/20217정진욱/Sans/Server.py'],
    pathex=['D:/20217정진욱/Sans'],
    binaries=[],
    datas=[('D:/20217정진욱/Sans/Image', 'Image'), ('D:/20217정진욱/Sans/Font', 'Font'), ('D:/20217정진욱/Sans/Sound', 'Sound')],
    hiddenimports=[],
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
    name='TheBattlesServer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='TheBattlesServer',
)
