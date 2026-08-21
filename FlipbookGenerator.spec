# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the self-contained Windows GUI executable."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


ffmpeg_datas, ffmpeg_binaries, ffmpeg_hiddenimports = collect_all("imageio_ffmpeg")
pillow_hiddenimports = collect_submodules("PIL")
python_root = Path(sys.base_prefix)
tk_dll_root = python_root / "DLLs"
tk_library_root = python_root / "tcl"
tk_binaries = [
    (str(tk_dll_root / "_tkinter.pyd"), "."),
    (str(tk_dll_root / "tcl86t.dll"), "."),
    (str(tk_dll_root / "tk86t.dll"), "."),
]
tk_datas = [
    (str(python_root / "Lib" / "tkinter"), "tkinter"),
    (str(tk_library_root / "tcl8.6"), "_tcl_data"),
    (str(tk_library_root / "tk8.6"), "_tk_data"),
]

a = Analysis(
    ["flipbook_gui.pyw"],
    pathex=[SPECPATH],
    binaries=ffmpeg_binaries + tk_binaries,
    datas=ffmpeg_datas + tk_datas,
    hiddenimports=(
        ffmpeg_hiddenimports + pillow_hiddenimports
        + ["_tkinter", "tkinterdnd2"]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["pyi_rth_flipbook_tk.py"],
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

