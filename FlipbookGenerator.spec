# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the self-contained Windows GUI executable."""

from PyInstaller.utils.hooks import collect_all, collect_submodules


ffmpeg_datas, ffmpeg_binaries, ffmpeg_hiddenimports = collect_all("imageio_ffmpeg")
pillow_hiddenimports = collect_submodules("PIL")

a = Analysis(
    ["flipbook_gui.pyw"],
    pathex=[SPECPATH],
    binaries=ffmpeg_binaries,
    datas=ffmpeg_datas,
    hiddenimports=ffmpeg_hiddenimports + pillow_hiddenimports + ["tkinterdnd2"],
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
    a.binaries,
    a.datas,
    [],
    name="FlipbookGenerator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

