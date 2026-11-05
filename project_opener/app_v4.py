"""Bootstrap of the Qt Quick (4.0) shell: ``python -m project_opener --v4``.  Owner: builder 4 (SHELL).

Order matters (spikes/quick/REPORT.md):
1. the Qt message handler first (QML errors are silent on Windows otherwise);
2. render backend before any window (software when the GPU probe says so);
3. ``QApplication`` (not QGuiApplication: the tray and native dialogs need QtWidgets);
4. single instance on ``SINGLE_INSTANCE_KEY_V4`` (forward and exit when one runs);
5. the facade, the QML engine with the context property ``app``, ``qml/Main.qml``;
6. the desktop integration (pill, hotkeys, tray), the socket, the CLI commands;
7. ``facade.start`` on the next turn of the event loop.

Source runs without ``--data-dir`` use a separate data folder (``ProjectOpener-v4dev``
next to the real one, seeded once from it) so a development run never migrates the
workspace an installed 3.2 is using.  Frozen builds use the real folder.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from project_opener import constants as C

log = logging.getLogger(__name__)

QML_DIR = Path(__file__).resolve().parent / "qml"


def qml_dir() -> Path:
    return C.bundle_dir() / "qml" if C.is_frozen() else QML_DIR


def _dev_data_dir() -> None:
    """Point PO_DATA_DIR at a v4 development copy unless a data dir was given or the app is frozen."""
    if C.is_frozen() or os.environ.get("PO_DATA_DIR"):
        return
    real = C.data_dir()
    dev = real.parent / f"{C.APP_ID}-v4dev"
    if not dev.exists():
        dev.mkdir(parents=True, exist_ok=True)
        for name in (C.WORKSPACE_FILE, C.SETTINGS_FILE):
            if (real / name).exists():
                shutil.copy2(real / name, dev / name)
    os.environ["PO_DATA_DIR"] = str(dev)


def _install_message_handler() -> None:
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
              QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}

    def handler(mode: Any, ctx: Any, msg: str) -> None:
        where = f" ({ctx.file}:{ctx.line})" if ctx is not None and ctx.file else ""
        log.log(levels.get(mode, logging.WARNING), "[qt] %s%s", msg, where)
        if mode != QtMsgType.QtDebugMsg:
            print(f"[qt] {msg}{where}", file=sys.stderr, flush=True)

    qInstallMessageHandler(handler)


def _choose_backend(facade: Any, app: Any) -> None:
    """Probe the machine once per adapter and pick the render backend before any window exists; the
    motion level follows (quick.motion).  ``QT_QUICK_BACKEND=software`` in the environment wins."""
    from project_opener.quick import motion as MO

    s = facade.ctx.settings
    screen = app.primaryScreen()
    size = (screen.size().width(), screen.size().height()) if screen is not None else None
    try:
        facts = MO.probe_machine(s.gpu_probe, size)
    except Exception:  # noqa: BLE001
        log.exception("machine probe failed; assuming a GPU")
        facts = MO.MachineFacts(screen_w=size[0], screen_h=size[1]) if size else MO.MachineFacts()
    backend = MO.resolve_backend(s.render_backend, facts)
    if os.environ.get("QT_QUICK_BACKEND", "").lower() == "software":
        backend = "software"
    if backend == "software":
        from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
    s.save()
    facade.ui.set_machine(facts, backend)
    log.info("render backend %s, motion %s (adapter %r, %sx%s)", backend, facade.ui.motion, facts.adapter,
             facts.screen_w, facts.screen_h)


def main(args: Any) -> int:
    from project_opener.core.logging_setup import setup_logging

    _dev_data_dir()
    log_path = setup_logging()
    log.info("%s %s starting the Qt Quick shell (frozen=%s)", C.APP_NAME, C.VERSION, C.is_frozen())
    _install_message_handler()

    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow  # noqa: F401  (root objects then come back typed as QQuickWindow)
    from PySide6.QtWidgets import QApplication

    from project_opener import ipc
    from project_opener.core import winutil

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    winutil.set_app_user_model_id(f"DexterityDesign.{C.APP_ID}")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(C.APP_NAME)
    app.setOrganizationName(C.COMPANY_SHORT)
    app.setApplicationVersion(C.VERSION)
    app.setQuitOnLastWindowClosed(False)

    cmds = ipc.commands_from_args(args)
    if ipc.forward(C.SINGLE_INSTANCE_KEY_V4, cmds):
        log.info("another v4 instance is running; forwarded %d command(s) and exiting", len(cmds))
        return 0
    # N files chosen in Explorer start N processes at once: one claims the instance, the rest wait for its
    # socket and forward (V4-SEAMS, builder 3 ask 1).
    if not ipc.claim_instance(C.SINGLE_INSTANCE_KEY_V4):
        ok = ipc.forward_retry(C.SINGLE_INSTANCE_KEY_V4, cmds)
        log.info("another v4 instance is starting; forwarded=%s", ok)
        return 0 if ok else 1
    server = ipc.InstanceServer(C.SINGLE_INSTANCE_KEY_V4)
    server.listen()

    from project_opener.ui import theme
    theme.load_fonts()

    from project_opener.desktop.integration import DesktopIntegration
    from project_opener.quick.facade import AppFacade

    facade = AppFacade()
    _choose_backend(facade, app)
    from PySide6.QtQuickControls2 import QQuickStyle
    QQuickStyle.setStyle("Basic")            # the shell styles every control itself; no native style warnings
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("app", facade)
    engine.load(QUrl.fromLocalFile(str(qml_dir() / "Main.qml")))
    if not engine.rootObjects():
        log.error("Main.qml failed to load (see the [qt] lines above)")
        return 2
    window = engine.rootObjects()[0]
    facade.ui.attach_window(window)
    try:
        from project_opener.core import winutil as _w
        _w.apply_dark_title_bar(int(window.winId()), facade.ui.dark)
    except Exception:  # noqa: BLE001
        pass

    desktop = DesktopIntegration(facade, engine, window)
    facade.set_desktop(desktop.api)
    desktop.start()

    def show_window() -> None:
        window.show()
        window.raise_()
        window.requestActivate()

    facade.showWindowRequested.connect(show_window)
    server.command.connect(facade.handle_command)
    if not (args.minimised or facade.ctx.settings.start_minimised):
        window.show()
    QTimer.singleShot(50, facade.start)
    for cmd in cmds:
        QTimer.singleShot(400, lambda c=cmd: facade.handle_command(c))
    if args.quit_after:
        QTimer.singleShot(int(args.quit_after), app.quit)

    rc = app.exec()
    desktop.shutdown()
    facade.shutdown()
    server.close()
    # Destroy the QML before the facade it binds to, or every binding reports "app is null" at exit.
    import shiboken6
    window = None
    shiboken6.delete(engine)
    log.info("exit %s (log: %s)", rc, log_path)
    return rc
