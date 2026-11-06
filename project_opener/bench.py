r"""``ProjectOpener.exe --bench [--out PATH]``: the release benchmark for any PC (the older-PC run).

Self-contained and harmless.  It runs in a throwaway data folder under %TEMP% (deleted afterwards), with no
Team Hub, no presence, no update check, no capture, no pill, tray or hot keys, and a dry-run launcher: nothing
is opened, no other window is read, moved or captured.  The only window it touches is its own.

What it does:

1. Probes the machine as a first start would (graphics adapter, D3D11 check, remote session, screen size,
   Windows animations, battery) and picks the render backend and the motion level the app would choose.
   It also reads, never writes, this user's saved settings to say what the installed app runs at now.
2. Shows the real main window on Home with a demo stage (Lot 7 check in the centre, two activities beside it).
   First frame: from process start to the window's first frame.
3. Idle memory and CPU: after the start-up settles, 5 s on Home.
4. Opens the demo activity's dock six times at each level (rich, purposeful, off).  Frames are measured as
   the app's own runtime guard measures them: over the grow (420 ms x the level's scale, plus 80 ms), after the
   first frame, the mean interval and the mean of the worst 1 %; the first frame after the click (the
   response time, the same at every level) is reported on its own.  A 5 ms heartbeat on the GUI thread gives the longest stall from
   the open until the rows have settled (at every level, off included).  The dry-run launcher takes about
   400 ms per item, so the rows settle as they would with real files.  After each change of level one
   opening is made and not counted: a level change re-binds every animation once, which a user meets only
   when changing the setting.
5. Prints a short summary (to stdout when it is redirected, else to the console it was started from),
   writes the JSON (``--out``; default next to the exe when that folder is writable, else %TEMP%) and a .txt with
   the same summary, then exits 0 (2 when the window could not load).
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from project_opener import constants as C

log = logging.getLogger(__name__)

LEVELS = ("rich", "purposeful", "off")
RUNS = 6
ITEM_MS = 400                  # dry-run pace per item
IDLE_S = 5.0
LEVEL_WORD = {"rich": "Rich", "purposeful": "Purposeful", "off": "Off"}
QML_CACHE_DIR = "po-bench-qmlcache"     # in %TEMP%; emptied at the start of every run


# ---------------------------------------------------------------- output
def attach_console() -> None:
    """Give the bench a stdout.  The exe is a windowed app, so Python starts it with ``sys.stdout = None``:

    1. stdout redirected to a file or a pipe (``ProjectOpener.exe --bench > bench.txt``, ``| Out-File``,
       ``Start-Process -RedirectStandardOutput``): write there, so the summary lands where it was sent;
    2. otherwise the console it was started from (``Start-Process -Wait -NoNewWindow``, cmd): attach to it;
    3. neither: print nothing (the JSON and the .txt are written either way)."""
    if sys.platform != "win32":
        return
    try:
        if sys.stdout is not None and sys.stdout.fileno() >= 0:
            return                                            # from source, or a console build
    except Exception:  # noqa: BLE001 - no usable stdout
        pass
    try:
        import ctypes
        import msvcrt
        k32 = ctypes.windll.kernel32
        k32.GetStdHandle.restype = ctypes.c_void_p
        handle = k32.GetStdHandle(-11)                        # STD_OUTPUT_HANDLE
        invalid = (None, 0, ctypes.c_void_p(-1).value)
        if handle not in invalid and k32.GetFileType(ctypes.c_void_p(handle)) in (1, 3):   # FILE_TYPE_DISK / PIPE
            fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)
            sys.stdout = open(fd, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)  # noqa: SIM115
            sys.stderr = sys.stdout
            return
        if k32.AttachConsole(-1):                             # ATTACH_PARENT_PROCESS
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")  # noqa: SIM115
            sys.stderr = sys.stdout
            print()
    except Exception:  # noqa: BLE001
        pass


def say(text: str = "") -> None:
    try:
        if sys.stdout is not None:
            print(text, flush=True)
    except Exception:  # noqa: BLE001
        pass


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / f".po-bench-{os.getpid()}.tmp"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:  # noqa: BLE001
        return False


def default_out(now: float | None = None, exe_dir: Path | None = None) -> Path:
    """``bench-<PC>-<date>-<time>.json`` next to the exe (the frozen build), else in %TEMP%."""
    stamp = time.strftime("%Y%m%d-%H%M", time.localtime(now or time.time()))
    pc = "".join(ch for ch in (os.environ.get("COMPUTERNAME") or platform.node() or "pc") if ch.isalnum() or ch in "-_")
    name = f"bench-{pc}-{stamp}.json"
    if exe_dir is None and C.is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
    if exe_dir is not None and _writable(exe_dir):
        return exe_dir / name
    return Path(tempfile.gettempdir()) / name


def resolve_out(path: str | None) -> Path:
    """``--out``: a .json file, or a folder to put the default name in; falls back to %TEMP% when not writable."""
    if not path:
        return default_out()
    p = Path(path).expanduser()
    if p.suffix.lower() != ".json":
        p = p / default_out().name
    if _writable(p.parent):
        return p
    return Path(tempfile.gettempdir()) / p.name


# ----------------------------------------------------------------- stats
def frame_stats(t0: float, stamps: list[float], window_ms: float) -> dict[str, Any]:
    """The guard's numbers for one opening (``motion.guard_stats``): over the frames within window_ms after
    the first, the mean interval and the mean of the worst 1 % (the single worst frame below 100 intervals);
    plus the response time (t0 to the first frame), the longest interval of all and the frame count."""
    from project_opener.quick import motion as MO
    pts = MO.window_stamps([t0] + [s for s in stamps if s > t0], window_ms)
    mean, worst = MO.guard_stats(pts)
    gaps = [(b - a) * 1000.0 for a, b in zip(pts, pts[1:], strict=False)]
    real = sum(1 for s in stamps if t0 < s <= t0 + window_ms / 1000.0)      # frames, not the window's end
    return {"frames": real, "mean_ms": mean, "worst1_ms": worst, "first_ms": MO.first_frame_ms(pts),
            "longest_ms": round(max(gaps), 1) if gaps else 0.0,
            "slow": MO.dock_frames_too_slow(mean, worst) if len(pts) >= 4 else False}


def gui_stalls(beats: list[float]) -> dict[str, Any]:
    """From heartbeat stamps (a 5 ms timer on the GUI thread): the longest gap and the gaps over 50 ms."""
    gaps = [(b - a) * 1000.0 for a, b in zip(beats, beats[1:], strict=False)]
    return {"gui_longest_ms": round(max(gaps), 1) if gaps else 0.0, "gui_over_50ms": sum(1 for g in gaps if g > 50)}


def level_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {}
    means = [r["mean_ms"] for r in runs if r["frames"]]
    worsts = [r["worst1_ms"] for r in runs if r["frames"]]
    stalls = [r.get("gui_longest_ms", 0.0) for r in runs]
    firsts = [r.get("first_ms", 0.0) for r in runs if r["frames"]]
    return {"runs": len(runs),
            "first_ms_median": round(statistics.median(firsts), 1) if firsts else 0.0,
            "first_ms_max": round(max(firsts), 1) if firsts else 0.0,
            "gui_longest_ms_median": round(statistics.median(stalls), 1) if stalls else 0.0,
            "gui_longest_ms_max": round(max(stalls), 1) if stalls else 0.0,
            "mean_ms": round(statistics.fmean(means), 1) if means else 0.0,
            "mean_ms_max": round(max(means), 1) if means else 0.0,
            "worst1_ms_median": round(statistics.median(worsts), 1) if worsts else 0.0,
            "worst1_ms_max": round(max(worsts), 1) if worsts else 0.0,
            "slow_runs": sum(1 for r in runs if r["slow"])}


def guard_verdict(level: str, runs: list[dict[str, Any]]) -> str:
    """What the app's runtime guard would do with these openings at ``level``: "" (stays) or the level it
    would drop to, after which opening it would happen."""
    from project_opener.quick import motion as MO
    g = MO.RuntimeGuard()
    for n, r in enumerate(runs, start=1):
        drop = g.report(level, r["mean_ms"], r["worst1_ms"])
        if drop:
            return f"{drop} after opening {n}"
    return ""


def summary_lines(res: dict[str, Any]) -> list[str]:
    """The plain-English summary (printed and written next to the JSON)."""
    m, a = res["machine"], res["app"]
    gpu = m.get("adapter") or "an unknown graphics adapter"
    scr = m.get("screen", {})
    lines = [f"Project Opener {res['version']} bench on {m.get('computer', 'this PC')}",
             f"  {m.get('cpu', '')}, {m.get('cores', '?')} cores, {m.get('ram_gb', '?')} GB RAM, {m.get('windows', '')}",
             f"  {gpu}; screen {scr.get('width')} x {scr.get('height')} at {scr.get('scale_pct')} % "
             f"({scr.get('refresh_hz')} Hz)"]
    render = "the graphics card (Direct3D 11)" if a["backend"] == "rhi" else "software rendering (no GPU)"
    lines.append(f"The app would draw with {render} and start in {LEVEL_WORD[a['motion_auto']]} motion"
                 f" ({a['motion_reason']}).")
    if a.get("motion_saved") and a["motion_saved"] != a["motion_auto"]:
        lines.append(f"  This user's saved settings run it at {LEVEL_WORD.get(a['motion_saved'], a['motion_saved'])}"
                     f" ({a.get('motion_saved_why', '')}).")
    st = res["start"]
    lines.append(f"First frame {st['first_frame_s']:.1f} s after launch "
                 f"({st['window_to_frame_ms']:.0f} ms from showing the window; a first start: the QML is "
                 f"compiled and the GPU probed afresh).")
    ph = st.get("phases_s") or {}
    if ph.get("qml_load") and ph.get("qml_load_warm") is not None:
        lines.append(f"  Building the window took {ph['qml_load']:.1f} s on this first start and "
                     f"{ph['qml_load_warm']:.1f} s once its QML is compiled, as on every later start.")
    idle = res["idle"]
    lines.append(f"Idle on Home: {idle['private_mb']:.0f} MB private memory ({idle['working_set_mb']:.0f} MB working set), "
                 f"{idle['cpu_pct_one_core']:.1f} % of one CPU core.")
    lines.append(f"Dock opening, {res.get('runs') or RUNS} times per level: the first frame after the click, the "
                 f"frames of the grow after it (the app reduces motion after two openings over 33 ms mean or "
                 f"120 ms worst 1 %) and the longest GUI stall:")
    for lvl in LEVELS:
        s = res["dock"].get(lvl, {}).get("summary") or {}
        if not s:
            continue
        stall = (f"first frame median {s.get('first_ms_median', 0):.0f} ms (max {s.get('first_ms_max', 0):.0f}); "
                 f"GUI stall median {s['gui_longest_ms_median']:.0f} ms (max {s['gui_longest_ms_max']:.0f})")
        if lvl == "off":
            lines.append(f"  Off         nothing animates; {stall}")
            continue
        verdict = res["dock"][lvl].get("guard") or ""
        tail = f"guard would reduce to {verdict}" if verdict else "within the limits"
        lines.append(f"  {LEVEL_WORD[lvl]:<11} mean {s['mean_ms']:.0f} ms (max {s['mean_ms_max']:.0f}), worst 1 % "
                     f"median {s['worst1_ms_median']:.0f} ms (max {s['worst1_ms_max']:.0f}), {s['slow_runs']} slow; "
                     f"{stall}; {tail}")
    lines.append("Verdict: " + res["verdict"])
    if res.get("qt_warnings"):
        lines.append(f"{len(res['qt_warnings'])} Qt warning(s) recorded (see the JSON).")
    return lines


def overall_verdict(auto: str, dock: dict[str, Any]) -> str:
    if auto == "off":
        return "this PC runs with motion off (remote session); nothing to hold."
    v = dock.get(auto, {}).get("guard") or ""
    if not v:
        return f"{LEVEL_WORD[auto]} motion holds on this PC."
    drop = v.split(" ", 1)[0]
    v2 = dock.get(drop, {}).get("guard") or ""
    if drop == "off" or not v2:
        return f"the guard would reduce {LEVEL_WORD[auto]} to {LEVEL_WORD[drop]} on this PC, which then holds."
    return f"the guard would reduce {LEVEL_WORD[auto]} to {LEVEL_WORD[drop]}, and that is slow too."


# --------------------------------------------------------------- machine
def machine_info(app: Any) -> dict[str, Any]:
    import psutil
    scr = app.primaryScreen()
    info: dict[str, Any] = {"computer": os.environ.get("COMPUTERNAME") or platform.node(),
                            "windows": platform.platform(), "python": platform.python_version(),
                            "cores": psutil.cpu_count(logical=True), "cores_physical": psutil.cpu_count(logical=False),
                            "ram_gb": round(psutil.virtual_memory().total / 2**30, 1)}
    info["cpu"] = _cpu_name()
    if scr is not None:
        g, dpr = scr.geometry(), scr.devicePixelRatio()
        info["screen"] = {"width": round(g.width() * dpr), "height": round(g.height() * dpr),
                          "logical_width": g.width(), "logical_height": g.height(), "scale_pct": round(dpr * 100),
                          "refresh_hz": round(scr.refreshRate()), "count": len(app.screens())}
    return info


def _cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except Exception:  # noqa: BLE001
            pass
    return platform.processor() or ""


def saved_settings() -> dict[str, Any]:
    """This user's settings.json, read only (the folder the installed app uses); {} when there is none."""
    if os.environ.get("PO_DATA_DIR"):
        folder = Path(os.environ["PO_DATA_DIR"])
    elif sys.platform == "win32":
        folder = Path(os.environ.get("APPDATA", Path.home())) / "DexterityDesign" / C.APP_ID
    else:
        folder = Path.home() / ".config" / "DexterityDesign" / C.APP_ID
    f = folder / C.SETTINGS_FILE
    try:
        data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


# ------------------------------------------------------------------ seed
def seed(data_dir: Path) -> str:
    """Three activities on the stage; returns the id of the one in the centre (Lot 7 check, 6 items)."""
    from project_opener.core import models as M
    from project_opener.core.settings import Settings
    from project_opener.core.store import WorkspaceStore

    files = data_dir / "demo" / "P12513"
    (files / "Lot 7").mkdir(parents=True, exist_ok=True)
    (files / "Revision C").mkdir(parents=True, exist_ok=True)
    names = ["Iso checklist.pdf", "Line list.xlsx", "Lot 7/Comment register.xlsx", "Rulings.docx",
             "P12513-ISO-1042-C.pdf"]
    for n in names:
        (files / n).write_bytes(b"bench")

    s = Settings.load(data_dir)
    s.display_name, s.role = "Bench", "Checker"
    s.hub_path = ""
    s.presence_udp = False
    s.update_check = False
    s.capture_enabled = False
    s.pill_enabled = False
    s.hotkeys_enabled = False
    s.first_run_done = True
    s.confirm_launch_over = 0
    s.start_minimised = False
    s.motion = "auto"
    s.save()

    # a fresh store imports Project Opener 1.x's projects from %APPDATA%\ProjectOpener: never in the bench (those
    # are the user's, and their health checks would reach the user's shares); 1.x is looked for in the work folder
    saved_appdata = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(data_dir.parent / "no-appdata")
    try:
        store = WorkspaceStore(data_dir)
    finally:
        if saved_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = saved_appdata
    store.projects.clear()
    p = M.Project(name="As-built isometrics", client="FST", job_number="P12513", color="#2F5BFF", icon="ph.compass",
                  items=[M.Item(path=str(files / "Iso checklist.pdf"), kind="file", group="Checking"),
                         M.Item(path=str(files / "Line list.xlsx"), kind="file", group="Checking"),
                         M.Item(path=str(files / "Lot 7" / "Comment register.xlsx"), kind="file", group="Checking"),
                         M.Item(path=str(files / "Lot 7"), kind="folder", group="Folders", label="Lot 7"),
                         M.Item(path=str(files / "Revision C"), kind="folder", group="Folders", label="Revision C"),
                         M.Item(path=str(files / "P12513-ISO-1042-C.pdf"), kind="file", group="Isos")])
    q = M.Project(name="ANTEO Isometrics", client="ANTEO", color="#10B981", icon="ph.anchor",
                  items=[M.Item(path=str(files / "Rulings.docx"), kind="file")])
    store.add(p)
    store.add(q)
    store.activities.clear()

    def items(proj: M.Project) -> list[M.ActivityItem]:
        out = []
        for it in proj.items:
            a = M.ActivityItem.from_item(it, proj.id, it.id)
            a.id = M.new_id()
            out.append(a)
        return out

    lot7 = M.Activity(name="Lot 7 check", short_name="Lot 7 check", icon="ph.checks", project_ids=[p.id],
                      items=items(p), pinned_at=M.now_iso())
    store.add_activity(lot7)
    store.add_activity(M.Activity(name="ANTEO handover", short_name="ANTEO", icon="ph.anchor", project_ids=[q.id],
                                  items=items(q)))
    store.add_activity(M.Activity(name="Clash review", short_name="Clash", icon="ph.cube", project_ids=[q.id],
                                  items=items(q)))
    store.save()
    try:
        store.close_writer(2.0)
    except Exception:  # noqa: BLE001
        pass
    return lot7.id


# ------------------------------------------------------------------- run
def _pump(app: Any, seconds: float) -> None:
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def _wait(app: Any, cond: Any, seconds: float, step: float = 0.05) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        _pump(app, step)
    return bool(cond())


def run(args: Any) -> int:
    """The bench.  ``args.out`` (path or None), ``args.bench_runs`` (int, default 6)."""
    import psutil

    t_entry = time.time()
    proc = psutil.Process()
    try:
        t_launch = proc.create_time()
    except Exception:  # noqa: BLE001
        t_launch = t_entry
    attach_console()
    runs = max(1, int(getattr(args, "bench_runs", 0) or RUNS))
    out = resolve_out(getattr(args, "out", None))
    saved = saved_settings()                       # before PO_DATA_DIR points at the throwaway folder

    work = Path(tempfile.mkdtemp(prefix="po-bench-"))
    data_dir = work / "data"
    data_dir.mkdir()
    os.environ["PO_DATA_DIR"] = str(data_dir)
    # a first start's QML compile, in a folder of its own: the QML engine keeps its .qmlc files mapped until the
    # process ends, so Windows cannot delete them at the end of the run; the next run empties it first
    qml_cache = Path(tempfile.gettempdir()) / QML_CACHE_DIR
    shutil.rmtree(qml_cache, ignore_errors=True)
    os.environ.setdefault("QML_DISK_CACHE_PATH", str(qml_cache))
    say(f"Project Opener {C.VERSION}: benchmark (about 2 minutes; please leave the PC alone).")
    say(f"Throwaway data folder: {work}")
    qt_warnings: list[str] = []
    try:
        return _run(args, runs, out, saved, work, data_dir, t_launch, t_entry, proc, qt_warnings)
    finally:
        root = logging.getLogger()
        for h in list(root.handlers):          # the log file lives in the throwaway folder
            if isinstance(h, logging.FileHandler):
                root.removeHandler(h)
                h.close()
        _release_qt()
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(qml_cache, ignore_errors=True)      # empty when Qt let go of it; else the next run does


def _release_qt() -> None:
    """Destroy the QApplication (the bench is the whole process), so Qt lets go of what it holds open."""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            import shiboken6
            shiboken6.delete(app)
    except Exception:  # noqa: BLE001
        pass


def _run(args: Any, runs: int, out: Path, saved: dict[str, Any], work: Path, data_dir: Path, t_launch: float,
         t_entry: float, proc: Any, qt_warnings: list[str]) -> int:
    from PySide6.QtCore import Qt, QtMsgType, QUrl, qInstallMessageHandler
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow  # noqa: F401
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtWidgets import QApplication

    from project_opener import app_v4
    from project_opener.core.logging_setup import setup_logging
    from project_opener.quick import motion as MO

    setup_logging()

    def handler(mode: Any, ctx: Any, msg: str) -> None:
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            where = f" ({ctx.file}:{ctx.line})" if ctx is not None and ctx.file else ""
            qt_warnings.append(f"{msg}{where}")
    qInstallMessageHandler(handler)

    phases: dict[str, float] = {"python_and_imports": time.time() - t_launch}
    t = time.time()
    lot7 = seed(data_dir)
    phases["seed"] = time.time() - t

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(C.APP_NAME + " bench")
    app.setOrganizationName(C.COMPANY_SHORT)
    app.setQuitOnLastWindowClosed(False)

    from project_opener.quick.facade import AppFacade
    from project_opener.ui import theme
    theme.load_fonts()
    facade = AppFacade(data_dir)
    facade.ctx.store.write_in_background()

    # the backend and level the app would choose on a first start (a fresh probe, no saved reduction)
    screen = app.primaryScreen()
    size = (screen.size().width(), screen.size().height()) if screen is not None else None
    t = time.perf_counter()
    try:
        facts = MO.probe_machine({}, size)
    except Exception:  # noqa: BLE001
        log.exception("probe failed")
        facts = MO.MachineFacts(screen_w=size[0], screen_h=size[1]) if size else MO.MachineFacts()
    probe_ms = (time.perf_counter() - t) * 1000
    phases["gpu_probe"] = probe_ms / 1000
    setting_backend = str(saved.get("render_backend") or "auto")
    backend = MO.resolve_backend(setting_backend if setting_backend in ("auto", "gpu", "software") else "auto", facts)
    if os.environ.get("QT_QUICK_BACKEND", "").lower() == "software":
        backend = "software"
    if backend == "software":
        from PySide6.QtQuick import QSGRendererInterface
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
    facade.ui.set_machine(facts, backend)
    auto = MO.auto_level(facts, backend)
    reason = facade.ui.motionReason.split(", ", 1)[-1].replace("\u00d7", "x")
    saved_motion = str(saved.get("motion") or "auto")
    saved_reduced = str(saved.get("motion_reduced_to") or "")
    saved_level = MO.resolve_motion(saved_motion if saved_motion in MO.SETTINGS else "auto", saved_reduced, facts, backend) \
        if saved else ""
    saved_why = ("your choice" if saved_motion in MO.LEVELS else
                 "reduced earlier by the runtime guard" if saved_reduced in MO.LEVELS and saved_level == saved_reduced
                 else "auto")

    # nothing is opened and capture never starts: the dock's rows settle at a real-looking pace
    facade.ctx.launcher.dry_run = True
    orig_open = facade.ctx.launcher.open_item

    def paced(item: Any, host_cache: Any = None) -> Any:
        time.sleep(ITEM_MS / 1000.0)
        return orig_open(item, host_cache)
    facade.ctx.launcher.open_item = paced           # type: ignore[method-assign]
    facade.capture.startActivity = lambda _aid: None    # type: ignore[method-assign]

    QQuickStyle.setStyle("Basic")
    t = time.time()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("app", facade)
    engine.load(QUrl.fromLocalFile(str(app_v4.qml_dir() / "Main.qml")))
    if not engine.rootObjects():
        say("The main window could not load: " + "; ".join(qt_warnings[:5]))
        return 2
    win = engine.rootObjects()[0]
    phases["qml_load"] = time.time() - t
    cache = app_v4.configure_pipeline_cache(win, data_dir, backend)
    facade.ui.attach_window(win)

    stamps: list[float] = []
    first: list[float] = []

    def on_frame() -> None:                         # render thread: a timestamp, nothing else
        now = time.perf_counter()
        if not first:
            first.append(time.time())
        stamps.append(now)
    win.frameSwapped.connect(on_frame, Qt.ConnectionType.DirectConnection)

    if screen is not None:
        avail = screen.availableGeometry()
        w = max(1040, min(1400, avail.width() - 40))
        h = max(660, min(860, avail.height() - 40))
        win.resize(w, h)
        win.setPosition(avail.x() + (avail.width() - w) // 2, avail.y() + (avail.height() - h) // 2)
    t_show = time.time()
    win.show()
    win.raise_()
    _pump(app, 0.05)
    facade.start()
    try:
        facade.ctx.hub_timer.stop()
    except Exception:  # noqa: BLE001
        pass
    _wait(app, lambda: bool(first), 30)
    first_frame_s = (first[0] - t_launch) if first else -1.0
    window_to_frame_ms = (first[0] - t_show) * 1000 if first else -1.0
    say(f"First frame {first_frame_s:.1f} s after launch.")

    # idle: the start-up settles (Home built, pre-warm done), then 5 s on Home
    _pump(app, 3.0)
    warmed = bool(win.property("dockWarmed"))
    proc.cpu_percent(None)
    _pump(app, IDLE_S)
    cpu = proc.cpu_percent(None)
    mem = proc.memory_info()
    idle = {"seconds": IDLE_S, "cpu_pct_one_core": round(cpu, 1),
            "cpu_pct_all_cores": round(cpu / max(1, psutil_cores()), 2),
            "working_set_mb": round(mem.rss / 2**20, 1),
            "private_mb": round(getattr(mem, "private", mem.rss) / 2**20, 1),
            "frames_while_idle": 0}
    n0 = len(stamps)
    _pump(app, 1.0)
    idle["frames_while_idle"] = len(stamps) - n0
    say(f"Idle: {idle['private_mb']:.0f} MB, {idle['cpu_pct_one_core']:.1f} % of one core.")

    from PySide6.QtCore import QTimer
    acts = facade.activities
    dock: dict[str, Any] = {}
    beat = QTimer()
    beat.setInterval(5)
    beat.setTimerType(Qt.TimerType.PreciseTimer)
    for level in LEVELS:
        facade.ui.setMotion(level)
        window_ms = MO.dock_measure_ms(level) or MO.dock_measure_ms("rich")    # off: the same span as rich
        rows: list[dict[str, Any]] = []
        for n in range(0, runs + 1):                    # 0: the settling opening after the level change
            if acts.property("dockOpen"):
                acts.closeDock()
            facade.ui.go("home", {})
            _pump(app, 1.0)
            beats: list[float] = []
            conn = beat.timeout.connect(lambda b=beats: b.append(time.perf_counter()))
            beat.start()
            _pump(app, 0.02)
            t0 = time.perf_counter()
            acts.open(lot7)
            _pump(app, window_ms / 1000.0 + 0.05)
            r = frame_stats(t0, list(stamps), window_ms)
            _wait(app, lambda: not acts.property("launching"), 30)
            r["settle_s"] = round(time.perf_counter() - t0, 1)
            _pump(app, 0.3)
            beat.stop()
            beat.timeout.disconnect(conn)
            r.update(gui_stalls(beats))
            r["summary"] = acts.property("launchSummary")
            _pump(app, 1.2)                             # Home's settle: all opened -> the activity page
            if n == 0:
                continue
            rows.append(r)
            say(f"  {LEVEL_WORD[level]:<11} opening {n}: first frame {r['first_ms']:.0f} ms, then mean "
                f"{r['mean_ms']:.0f} ms, worst 1 % {r['worst1_ms']:.0f} ms ({r['frames']} frames in {window_ms} ms);"
                f" longest GUI stall {r['gui_longest_ms']:.0f} ms")
        if acts.property("dockOpen"):
            acts.closeDock()
        dock[level] = {"measure_ms": window_ms, "runs": rows, "summary": level_summary(rows),
                       "guard": guard_verdict(level, rows) if level != "off" else ""}
    facade.ui.go("home", {})
    _pump(app, 0.5)

    # a later start: the same QML again, now from the compiled cache (a hidden second window, then dropped)
    t = time.time()
    engine2 = QQmlApplicationEngine()
    engine2.rootContext().setContextProperty("app", facade)
    engine2.load(QUrl.fromLocalFile(str(app_v4.qml_dir() / "Main.qml")))
    phases["qml_load_warm"] = time.time() - t
    import shiboken6
    shiboken6.delete(engine2)
    _pump(app, 0.2)

    api = ""
    try:
        api = str(win.rendererInterface().graphicsApi()).split(".")[-1]
    except Exception:  # noqa: BLE001
        pass
    res: dict[str, Any] = {
        "bench": 1, "version": C.VERSION, "frozen": C.is_frozen(),
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "runs": runs, "item_ms": ITEM_MS,
        "machine": {**machine_info(app), "adapter": facts.adapter, "gpu_ok": facts.gpu_ok,
                    "remote_session": facts.remote_session, "animations_off": facts.animations_off,
                    "on_battery": facts.on_battery, "probe_ms": round(probe_ms)},
        "app": {"backend": backend, "graphics_api": api, "motion_auto": auto, "motion_reason": reason,
                "motion_saved": saved_level, "motion_saved_why": saved_why if saved else "",
                "render_backend_setting": setting_backend, "pipeline_cache": str(cache) if cache else "",
                "dock_prewarmed": warmed},
        "start": {"first_frame_s": round(first_frame_s, 2), "window_to_frame_ms": round(window_to_frame_ms),
                  "entry_to_frame_s": round((first[0] - t_entry), 2) if first else -1,
                  "phases_s": {k: round(v, 2) for k, v in phases.items()}},
        "idle": idle, "dock": dock, "limits": {"mean_ms": MO.SLOW_MEAN_MS, "worst1_ms": MO.SLOW_WORST1_MS},
        "qt_warnings": qt_warnings[:50],
    }
    res["verdict"] = overall_verdict(auto, dock)
    lines = summary_lines(res)
    res["summary"] = lines

    win.hide()
    facade.shutdown()
    import shiboken6
    shiboken6.delete(engine)
    # Qt writes the pipeline cache as the window's QRhi goes; on D3D11 it stays empty (Qt Quick's shaders ship
    # compiled, nothing is compiled at run time), on OpenGL it holds the linked programs
    res["app"]["pipeline_cache_bytes"] = cache.stat().st_size if cache is not None and cache.is_file() else 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    txt = out.with_suffix(".txt")
    txt.write_text("\n".join(lines) + f"\n\nJSON: {out}\n", encoding="utf-8")
    say("")
    for line in lines:
        say(line)
    say("")
    say(f"Results: {out}")
    say(f"Summary: {txt}")
    return 0


def psutil_cores() -> int:
    import psutil
    return psutil.cpu_count(logical=True) or 1


def main(args: Any) -> int:
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001
        import traceback
        say("The bench failed: " + repr(exc))
        say(traceback.format_exc())
        return 1
