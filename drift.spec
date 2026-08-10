# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Drift — single-file Windows build.

Build:  .venv\\Scripts\\pyinstaller.exe drift.spec --noconfirm
Output: dist\\Drift.exe
"""
from PyInstaller.utils.hooks import collect_data_files

datas = [("assets", "assets")]          # app icon + bundled fonts
datas += collect_data_files("docx")     # python-docx ships XML templates

# Everything is statically imported, but list the plugin-style packages so a
# future dynamic loader can't silently drop them from the bundle.
hiddenimports = [
    "db.migrations",
    "core.sources.definitions",
]

excludes = [
    "tkinter", "pytest", "PyInstaller",
    "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngine",
    "PyQt5.QtBluetooth", "PyQt5.QtNfc", "PyQt5.QtQuick3D", "PyQt5.QtMultimedia",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Drift",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,               # GUI app — no console window
    icon="assets/logo/drift.ico",
    version=None,
)
