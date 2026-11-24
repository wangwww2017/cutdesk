# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）。

本机实测 --onefile 的 bootloader 会残留进程与 _MEI 临时目录，因此统一使用 onedir。
"""

import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve()

EXCLUDES = [
    # 标准库中体量大且用不到的部分
    "tkinter",
    "unittest",
    "pydoc_data",
    "test",
    "lib2to3",
    "sqlite3",
    # 用不到的 Qt 模块：显著减小体积
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DQuick",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickTest",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtUiTools",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtRemoteObjects",
    "PySide6.QtSensors",
    "PySide6.QtTextToSpeech",
    "PySide6.QtHttpServer",
    "PySide6.QtDBus",
    "PySide6.QtPrintSupport",
    # 科学计算栈
    "matplotlib",
    "scipy",
    "pandas",
    "PIL",
]

a = Analysis(
    ["run.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=["soundcard", "mss", "cffi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ---- 精简二进制：剔除用不到的大块 Qt 组件 ----
# opengl32sw 是软件 OpenGL 回退实现，Windows 上 Qt6 默认走 D3D11/WARP，用不到
DROP_BINARIES = {
    "opengl32sw.dll",
    "qt6quick.dll",
    "qt6qml.dll",
    "qt6qmlmodels.dll",
    "qt6qmlmeta.dll",
    "qt6qmlworkerscript.dll",
    "qt6pdf.dll",
    "qt6virtualkeyboard.dll",
}

a.binaries = [b for b in a.binaries if Path(b[0]).name.lower() not in DROP_BINARIES]


def _keep_data(entry) -> bool:
    name = str(entry[0]).replace("\\", "/").lower()
    if "/translations/" in name:
        # 只保留简体中文，其余语言包删掉
        return "zh_cn" in name
    return True


a.datas = [d for d in a.datas if _keep_data(d)]

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CutDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CutDesk",
)
