# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for Project Opener.

    pyinstaller project_opener.spec --noconfirm

Produces dist/ProjectOpener/ProjectOpener.exe (one-folder build: fastest
start-up and the layout the Inno Setup script expects).
"""
import os
import sys

sys.path.insert(0, os.path.abspath("."))
from project_opener import __version__  # noqa: E402

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=[],
    datas=[("project_opener/resources", "resources")],
    hiddenimports=["qtawesome", "PySide6.QtSvg", "PySide6.QtNetwork"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim Qt modules the app never loads.
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtQml",
        "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.Qt3DCore",
        "PySide6.Qt3DRender", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc",
        "PySide6.QtSerialPort", "PySide6.QtSensors", "PySide6.QtPositioning", "PySide6.QtLocation",
        "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
        "PySide6.QtWebSockets", "PySide6.QtWebChannel", "PySide6.QtHttpServer", "PySide6.QtGraphs",
        "PySide6.QtSpatialAudio", "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtHelp", "PySide6.QtSql",
        "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtPrintSupport", "PySide6.QtXml",
        "PySide6.QtConcurrent", "PySide6.QtDBus", "PySide6.QtAsyncio",
        "tkinter", "unittest", "pydoc", "doctest", "xmlrpc", "pytest",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ProjectOpener",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="project_opener/resources/icon/app.ico",
    version="build/version_info.txt" if os.path.exists("build/version_info.txt") else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ProjectOpener",
)
