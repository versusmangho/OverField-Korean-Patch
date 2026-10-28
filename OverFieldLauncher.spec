# -*- mode: python ; coding: utf-8 -*-

import os

a = Analysis(
    ['OverFieldLauncher.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Qt 6.11 uses the Windows ICU API (unversioned ucnv_* exports).
# A build-machine PATH entry such as Poppler can supply a different icuuc.dll
# with version-suffixed exports. Do not bundle it or its private data DLLs:
# the Windows loader must resolve ICU from the target's System32 directory.
if os.name == 'nt':
    a.binaries = [
        entry for entry in a.binaries
        if not (
            os.path.basename(entry[0]).lower().startswith('icu')
            and entry[0].lower().endswith('.dll')
        )
    ]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OverFieldLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
