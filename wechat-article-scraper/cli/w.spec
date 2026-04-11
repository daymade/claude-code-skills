# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for building single-file executable
Usage: pyinstaller w.spec --clean
"""

import sys
from pathlib import Path

# Get spec file directory (available as SPECPATH in PyInstaller)
spec_dir = Path(SPECPATH)  # noqa: F821
project_root = spec_dir.parent
scripts_dir = project_root / "scripts"

block_cipher = None

a = Analysis(
    [str(spec_dir / 'w_cli.py')],
    pathex=[
        str(project_root),
        str(scripts_dir),
        str(spec_dir),
    ],
    binaries=[],
    datas=[
        # Include any data files if needed
        (str(project_root / "web"), "web"),
    ],
    hiddenimports=[
        'typer',
        'rich',
        'rich.console',
        'rich.table',
        'rich.progress',
        'rich.panel',
        'rich.box',
        'requests',
        'bs4',
        'html2text',
        'markdownify',
        'openpyxl',
        'reportlab',
        'scrapling',
        'jinja2',
        'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'tkinter',
        'PIL',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='w',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Icon for the executable
    # icon=str(project_root / "assets" / "icon.ico"),
)
