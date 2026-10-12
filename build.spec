# build.spec
# This is the PyInstaller build script for ReelForge

import sys
import os
import customtkinter

# Find the path to the customtkinter assets
ctk_assets_path = os.path.join(os.path.dirname(customtkinter.__file__), "assets")

# --- Analysis: Find all our code ---
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (ctk_assets_path, 'customtkinter/assets')  # <-- CRITICAL: This bundles the themes
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None
)

# --- PYG: Package the app ---
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# --- EXE: Define the executable ---
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ReelForge',          # The name of your final binary
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,               # <-- IMPORTANT: False = No terminal window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None                    # You can add a path to an '.ico' file here
)