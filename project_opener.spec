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

# comtypes generates its UIAutomationCore wrapper (used by capture.sources.browser) into comtypes.gen on
# first use.  A frozen app cannot write there, so generate it now and ship the generated modules.
_comtypes_gen = []
try:
    import comtypes.client
    from PyInstaller.utils.hooks import collect_submodules

    comtypes.client.GetModule("UIAutomationCore.dll")
    _comtypes_gen = collect_submodules("comtypes.gen")
except Exception as exc:  # noqa: BLE001  (a build on a machine without UIA still produces an exe)
    print(f"WARNING: comtypes UIAutomationCore wrapper not generated: {exc}")

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=[],
    # v4: the QML tree ships next to the resources (app_v4.qml_dir() reads <bundle>/qml when frozen).
    datas=[("project_opener/resources", "resources"), ("project_opener/qml", "qml")],
    hiddenimports=[
        "qtawesome", "PySide6.QtSvg", "PySide6.QtNetwork",
        # v4: the Qt Quick shell, capture/restore (pywin32 + comtypes UIA), process info
        "PySide6.QtQml", "PySide6.QtQuick",
        "win32com", "win32com.client", "pythoncom", "pywintypes", "win32gui", "win32con", "win32api",
        "win32process", "comtypes", "comtypes.client", "psutil",
        # v4 desktop: the Send to shortcut (IShellLink) and the native pieces under ctypes
        "win32com.shell", "win32com.shell.shell", "winreg",
        *_comtypes_gen,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim Qt modules the app never loads.
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.Qt3DCore",
        "PySide6.Qt3DRender", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc",
        "PySide6.QtSerialPort", "PySide6.QtSensors", "PySide6.QtPositioning", "PySide6.QtLocation",
        "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
        "PySide6.QtWebSockets", "PySide6.QtWebChannel", "PySide6.QtHttpServer", "PySide6.QtGraphs",
        "PySide6.QtSpatialAudio", "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtHelp", "PySide6.QtSql",
        # not PySide6.QtOpenGL: PySide6.QtQuick imports it (the frozen shell failed with "libshiboken: could not
        # import module 'PySide6.QtOpenGL'" when it was excluded)
        "PySide6.QtOpenGLWidgets", "PySide6.QtPrintSupport", "PySide6.QtXml",
        "PySide6.QtConcurrent", "PySide6.QtDBus", "PySide6.QtAsyncio",
        "tkinter", "unittest", "pydoc", "doctest", "xmlrpc", "pytest",
    ],
    noarchive=False,
    optimize=1,
)
# v4 packaging notes:
# * comtypes' UIAutomationCore wrapper is generated above and shipped as hidden imports.
# * The QML tree (qml/, including qml/desktop for the pill, its panel and the picker) ships as data.
# * If the shell uses QtQuick.Controls, keep only the Basic style's QML plugins.
# * Check the installed size and first-frame time against spikes/quick/REPORT.md after the first build.
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
