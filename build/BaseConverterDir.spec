# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir + windowed）。

在项目根目录执行（推荐直接用 build/build.ps1）：
    python -m PyInstaller --noconfirm --clean build/BaseConverterDir.spec

生成目录：build/dist/BaseConverterDir/
发布时将 BaseConverterDir.exe 重命名为 进制转换演示器.exe，并与 _internal 一起复制到项目根目录。
"""

import os

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
BUILD_DIR = SPECPATH

a = Analysis(
    [os.path.join(PROJECT_ROOT, "main.py")],
    pathex=[PROJECT_ROOT],
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
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BaseConverterDir",
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
    version=os.path.join(BUILD_DIR, "version_info.txt"),
    icon=[os.path.join(PROJECT_ROOT, "assets", "app.ico")],
    manifest=os.path.join(BUILD_DIR, "app.manifest"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BaseConverterDir",
)
