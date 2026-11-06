"""Application bootstrap.  4.0's Qt Quick shell (``app_v4``) is the default; the 3.2 widgets UI below stays
reachable with ``--classic`` (or ``PO_UI=classic``) until 4.0 ships, then it can go."""
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


def deep_link_key(text: str) -> str:
    """The project id or name inside a ``projectopener://open/<key>`` link, URL-decoded.

    Windows passes the link exactly as registered, so a name with spaces
    arrives as ``%20``; the stored name never does.  Anything else gives "".
    """
    from urllib.parse import unquote
    text = (text or "").strip()
    prefix = f"{C.URI_SCHEME}://open/"
    if not text.startswith(prefix):
        return ""
    return unquote(text[len(prefix):].strip("/"))


def classic_requested(args: argparse.Namespace) -> bool:
    """The 3.2 widgets UI: ``--classic`` or ``PO_UI=classic``.  The v4-only commands (Explorer verb, Send to,
    --snapshot, --start-from-open) always go to the v4 shell, and ``--v4`` / ``PO_UI=quick`` win over both."""
    import os
    if args.v4 or os.environ.get("PO_UI", "").lower() == "quick":
        return False
    if args.add or args.sendto or args.snapshot or args.start_from_open:
        return False
    return bool(args.classic or os.environ.get("PO_UI", "").lower() == "classic")


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
    # v4 (docs/V4-ARCHITECTURE.md section 8).  The Qt Quick shell is the default; --classic is 3.2's UI.
    parser.add_argument("--v4", action="store_true", help=argparse.SUPPRESS)        # the default; kept for old shortcuts
    parser.add_argument("--classic", action="store_true", help="start the 3.2 widgets UI instead (until 4.0 ships)")
    parser.add_argument("--add", nargs="+", metavar="PATH", help="add paths to the running activity (Explorer verb)")
    parser.add_argument("--sendto", nargs="+", metavar="PATH", help="Send to > Project Opener")
    parser.add_argument("--snapshot", action="store_true", help="checkpoint the running activity")
    parser.add_argument("--start-from-open", action="store_true", help="start an activity from what is open")
    parser.add_argument("--quit-after", type=int, default=0, metavar="MS", help=argparse.SUPPRESS)
    parser.add_argument("--bench", action="store_true",
                        help="measure this PC (start, idle, the dock at each motion level) in a throwaway "
                             "data folder, print a summary, write a JSON file and exit")
    parser.add_argument("--out", metavar="PATH", help="with --bench: the JSON file or folder to write to "
                                                      "(default: next to the exe, else %%TEMP%%)")
    parser.add_argument("--bench-runs", type=int, default=0, help=argparse.SUPPRESS)   # tests: fewer openings
    parser.add_argument("target", nargs="?", help="projectopener://open|activity|task/<key> deep link")
    args = parser.parse_args(argv)
    if args.bench:
        # before anything picks a data folder or claims the single instance: the bench runs beside a
        # running Project Opener in a folder of its own and touches nothing of the user's
        from project_opener import bench
        return bench.main(args)
    if args.data_dir:
        import os
        os.environ["PO_DATA_DIR"] = args.data_dir
    from project_opener import app_v4
    # From source without --data-dir both UIs use the v4 development folder: the store migrates a 3.x
    # workspace to schema 4 on load, and the installed 3.2 must keep reading its own.
    app_v4.dev_data_dir()
    if not classic_requested(args):
        from project_opener import app_v4
        return app_v4.main(args)

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
                key = deep_link_key(line)
                if key:
                    proj = ctx.store.get(key) or ctx.store.by_name(key)
                    if proj:
                        ctx.launch(proj, parent=window)
        conn.readyRead.connect(read)

    server.newConnection.connect(on_connection)

    if args.minimised or s.start_minimised:
        window.hide()
    else:
        window.show()
    winutil.apply_dark_title_bar(int(window.winId()), dark)
    QTimer.singleShot(50, ctx.start)
    key = deep_link_key(args.target or "")
    if key:
        proj = ctx.store.get(key) or ctx.store.by_name(key)
        if proj:
            QTimer.singleShot(600, lambda: ctx.launch(proj, parent=window))
    if args.quit_after:
        QTimer.singleShot(int(args.quit_after), app.quit)
    rc = app.exec()
    log.info("exit %s (log: %s)", rc, log_path)
    return rc
