"""Application bootstrap: single instance, logging, theme, crash guard, window."""
from __future__ import annotations

import argparse
import logging
import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from project_opener import constants as C
from project_opener.core import winutil
from project_opener.core.logging_setup import setup_logging
from project_opener.ui import icons, theme
from project_opener.ui.context import AppContext
from project_opener.ui.main_window import MainWindow, _system_dark

log = logging.getLogger(__name__)


def _forward_to_running_instance(argv: list[str]) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(C.SINGLE_INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(("\n".join(["show", *argv]) + "\n").encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def _install_excepthook(app: QApplication) -> None:
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Unhandled exception:\n%s", text)
        try:
            box = QMessageBox()
            box.setWindowTitle("Project Opener hit a problem")
            box.setIcon(QMessageBox.Icon.Critical)
            box.setText("Something went wrong, but your workspace is safe (it is saved after every change).")
            box.setDetailedText(text)
            box.exec()
        except Exception:  # noqa: BLE001
            pass
    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="project-opener", add_help=True)
    parser.add_argument("--minimised", action="store_true", help="start hidden in the tray")
    parser.add_argument("--data-dir", help="use a different data folder (testing)")
    parser.add_argument("--version", action="version", version=f"{C.APP_NAME} {C.VERSION}")
    parser.add_argument("target", nargs="?", help="projectopener://open/<project-id-or-name> deep link")
    args = parser.parse_args(argv)
    if args.data_dir:
        import os
        os.environ["PO_DATA_DIR"] = args.data_dir

    log_path = setup_logging()
    log.info("%s %s starting (frozen=%s)", C.APP_NAME, C.VERSION, C.is_frozen())

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    winutil.set_app_user_model_id(f"DexterityDesign.{C.APP_ID}")
    app = QApplication(sys.argv)
    app.setApplicationName(C.APP_NAME)
    app.setOrganizationName(C.COMPANY_SHORT)
    app.setApplicationVersion(C.VERSION)
    app.setWindowIcon(icons.app_icon())
    app.setQuitOnLastWindowClosed(False)

    if _forward_to_running_instance([args.target] if args.target else []):
        log.info("another instance is running; forwarded and exiting")
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(C.SINGLE_INSTANCE_KEY)
    server.listen(C.SINGLE_INSTANCE_KEY)

    _install_excepthook(app)
    ctx = AppContext()
    s = ctx.settings
    dark = s.theme == "dark" or (s.theme == "system" and _system_dark())
    theme.apply_theme(app, dark, s.accent, s.density)

    window = MainWindow(ctx)

    def on_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def read() -> None:
            data = bytes(conn.readAll()).decode("utf-8", "ignore").split("\n")
            window.show_normal()
            for line in data:
                if line.startswith(f"{C.URI_SCHEME}://open/"):
                    key = line.split("/open/", 1)[1].strip("/")
                    proj = ctx.store.get(key) or ctx.store.by_name(key)
                    if proj:
                        ctx.launch(proj)
        conn.readyRead.connect(read)

    server.newConnection.connect(on_connection)

    if args.minimised or s.start_minimised:
        window.hide()
    else:
        window.show()
    winutil.apply_dark_title_bar(int(window.winId()), dark)
    QTimer.singleShot(50, ctx.start)
    if args.target and args.target.startswith(f"{C.URI_SCHEME}://open/"):
        key = args.target.split("/open/", 1)[1].strip("/")
        proj = ctx.store.get(key) or ctx.store.by_name(key)
        if proj:
            QTimer.singleShot(600, lambda: ctx.launch(proj))
    rc = app.exec()
    log.info("exit %s (log: %s)", rc, log_path)
    return rc
