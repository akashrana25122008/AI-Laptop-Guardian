# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AI Laptop Guardian.

Build folder-based distribution (not single .exe) for
maximum reliability on Windows.

Run from project root:
    pyinstaller AI-Laptop-Guardian.spec
"""

import os
import sys

block_cipher = None

# Exclude everything that must NOT be bundled into the
# portable build: credentials, tokens, cloud data, virtual
# environments, tests, and development files.

EXCLUDES = [
    "tkinter.test",
    "unittest",
    "test",
    "pytest",
    "py.test",
    "numpy",
    "pandas",
    "matplotlib",
    "scipy",
    "PIL",
    "cv2",
    "torch",
    "tensorflow",
]

# Hidden imports that PyInstaller may miss but the app
# needs at runtime.

HIDDEN_IMPORTS = [
    "psutil",
    "ollama",
    "customtkinter",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI-Laptop-Guardian",
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AI-Laptop-Guardian",
)
