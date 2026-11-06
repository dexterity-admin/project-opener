"""``app.ui``: theme tokens, motion level, routing, icons, the command palette.  Owner: builder 4 (SHELL).

Tokens are ``ui.theme.build_tokens`` as a QVariantMap (the QML never holds a raw
colour).  The motion level follows ``quick.motion`` and the runtime guard: the
shell brackets every dock opening with ``beginDockMeasure``/``endDockMeasure``;
the frame stamps come from ``QQuickWindow.frameSwapped`` (a direct connection
that only appends a timestamp, never Python work on the render thread).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

from project_opener.quick import motion as MO
from project_opener.quick.base import ApiBase, ro
from project_opener.quick.listmodel import DictListModel
from project_opener.ui import text as T

log = logging.getLogger(__name__)

ROUTES = ("home", "activity", "activities", "projects", "project", "hub", "updates", "settings")
MIN_W, MIN_H = 1040, 660
RAIL_W = 68
PALETTE_ROLES = ("rowKey", "rowKind", "group", "title", "subtitle", "glyph", "dotColor", "shortcut", "action",
                 "target")
PALETTE_LIMIT = 8                      # rows per group

# 3.x Font Awesome names kept on migrated activities/projects -> Phosphor (brief: the shell maps them).
FA_TO_PH = {
    "rocket": "rocket-launch", "folder": "folder", "folder-open": "folder-open", "drafting-compass": "compass",
    "ship": "anchor", "industry": "factory", "cubes": "cube", "cube": "cube", "tools": "wrench", "wrench": "wrench",
    "file-signature": "signature", "file-pdf": "file-pdf", "file": "file", "clipboard-check": "clipboard-text",
    "check": "check", "tasks": "checks", "project-diagram": "tree-structure", "ruler": "ruler",
    "hard-hat": "hard-hat", "building": "buildings", "map": "map-trifold", "pencil-ruler": "ruler",
    "search": "magnifying-glass", "users": "users-three", "calendar": "calendar", "star": "star", "bolt": "lightning",
}
DARK_ACCENT = "#3BC98F"
DEFAULT_ACTIVITY_ICON = "stack"
DEFAULT_PROJECT_ICON = "folder"

_PH_MAP: dict[str, int] | None = None
_PH_FAMILY = ""


def _argb(rgba: str) -> str:
    """"rgba(16,24,20,0.12)" -> "#1F101814" (QML colours cannot be written as rgba())."""
    try:
        r, g, b, a = (float(x) for x in rgba[rgba.index("(") + 1:rgba.index(")")].split(","))
    except ValueError:
        return "#33000000"
    return f"#{round(a * 255):02X}{int(r):02X}{int(g):02X}{int(b):02X}"


def tokens_for(dark: bool, accent: str, density: str) -> dict[str, Any]:
    """``theme.build_tokens`` as a map, plus the QML-only ones: ``shadow_q`` (the floating surfaces'
    shadow as #AARRGGBB, dark only), ``scrim`` (the 40 % ink behind a sheet), ``shadow_soft`` (its outer
    ring, dark only; both are transparent on light, where the border_strong ring alone floats a surface)."""
    from project_opener.ui import theme
    t = dict(dataclasses.asdict(theme.build_tokens(dark=dark, accent=accent, density=density)))
    if dark and (accent or "").upper() == theme.DEFAULT_ACCENT.upper():
        # docs/DESIGN.md's dark accent for the default green (#3BC98F, ink on it); build_tokens' generic
        # lightening gives #62A994, which reads as a disabled control on the Stage's dark ground.
        t.update(accent=DARK_ACCENT, accent_fg="#0F1211", accent_hover="#5ED3A3", accent_soft="#163A2C")
    # The floating shadow is two offset rings (the software renderer has no blur).  On dark they read as
    # depth; on light they read as a misregistered grey slab, so light keeps only the surface's own 1 px
    # border_strong ring and both offset rings are transparent (juror round 1, D4).
    t["shadow_q"] = _argb(t["shadow"]) if dark else "#00000000"
    t["shadow_soft"] = "#26000000" if dark else "#00000000"
    t["scrim"] = "#8C000000" if dark else "#66141A17"
    t["face"] = theme.FONT_FAMILY
    return t


def system_dark() -> bool:
    """Windows' app mode (AppsUseLightTheme = 0 means dark).  False off Windows."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def resolve_dark(mode: str) -> bool:
    if mode == "light":
        return False
    if mode == "system":
        return system_dark()
    return True                         # dark by default (brief section 4)


def _phosphor_files() -> tuple[Path, Path] | None:
    try:
        import qtawesome
    except Exception:  # noqa: BLE001
        return None
    fonts = Path(qtawesome.__file__).resolve().parent / "fonts"
    ttf = sorted(fonts.glob("phosphor-*.ttf"))
    cmap = sorted(fonts.glob("phosphor-charmap-*.json"))
    return (ttf[-1], cmap[-1]) if ttf and cmap else None


def phosphor() -> tuple[str, dict[str, int]]:
    """(font family, name -> code point) for the Phosphor icon font shipped with qtawesome.
    The font is registered with Qt on first use (needs a QGuiApplication)."""
    global _PH_MAP, _PH_FAMILY
    if _PH_MAP is None:
        _PH_MAP = {}
        files = _phosphor_files()
        if files:
            ttf, cmap = files
            with open(cmap, encoding="utf-8") as fh:
                raw = json.load(fh)
            _PH_MAP = {k: (int(v, 16) if isinstance(v, str) else int(v)) for k, v in raw.items()}
            try:
                from PySide6.QtGui import QFontDatabase
                fid = QFontDatabase.addApplicationFont(str(ttf))
                fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                _PH_FAMILY = fams[0] if fams else ""
            except Exception:  # noqa: BLE001
                log.warning("could not register the Phosphor icon font")
    return _PH_FAMILY, _PH_MAP


def icon_name(name: str, default: str = DEFAULT_ACTIVITY_ICON) -> str:
    """A stored icon name ("ph.ruler", "fa5s.ship", "ruler") as a Phosphor name the font has."""
    n = (name or "").strip()
    if n.startswith("ph."):
        n = n[3:]
    elif "." in n:
        n = FA_TO_PH.get(n.split(".", 1)[1], default)
    _, cmap = phosphor()
    if cmap and n not in cmap:
        return default if default in cmap else ""
    return n or default


class UiState(ApiBase):
    tokensChanged = Signal()
    motionChanged = Signal()
    routeChanged = Signal()
    motionReduced = Signal(str)              # message said once
    paletteChanged = Signal()

    def __init__(self, app: Any):
        super().__init__(app)
        s = app.ctx.settings
        self._theme_mode = s.theme if s.theme in ("dark", "light", "system") else "dark"
        self._dark = resolve_dark(self._theme_mode)
        self._tokens = tokens_for(self._dark, s.accent, s.density)
        self._facts = MO.MachineFacts()
        self._backend = MO.resolve_backend(s.render_backend, self._facts)
        self._motion = MO.resolve_motion(s.motion, s.motion_reduced_to, self._facts, self._backend)
        self._route = "home"
        self._route_payload: dict[str, Any] = {}
        self._history: list[tuple[str, dict[str, Any]]] = []
        self._guard = MO.RuntimeGuard()
        self._stamps: list[float] | None = None
        self._window: Any = None
        self._palette = DictListModel(PALETTE_ROLES, key="rowKey", parent=self)
        self._palette_query = ""
        family, _ = phosphor()
        self._icon_family = family

    # ----------------------------------------------------------- machine
    def set_machine(self, facts: MO.MachineFacts, backend: str) -> None:
        """``app_v4`` calls this after probing, before the QML loads."""
        s = self.app.ctx.settings
        self._facts, self._backend = facts, backend
        self._motion = MO.resolve_motion(s.motion, s.motion_reduced_to, facts, backend)
        self.motionChanged.emit()

    def attach_window(self, window: Any) -> None:
        """Record frame stamps for the runtime guard (only while a dock opening is measured)."""
        self._window = window
        try:
            window.frameSwapped.connect(self._on_frame, Qt.ConnectionType.DirectConnection)
        except Exception:  # noqa: BLE001
            log.debug("frameSwapped not available")

    def _on_frame(self) -> None:          # render thread: a timestamp, nothing else
        st = self._stamps
        if st is not None:
            st.append(time.perf_counter())

    # -------------------------------------------------------- properties
    tokens = ro("QVariantMap", "_tokens", tokensChanged)
    dark = ro(bool, "_dark", tokensChanged)
    themeMode = ro(str, "_theme_mode", tokensChanged)
    motion = ro(str, "_motion", motionChanged)          # rich | purposeful | off
    backend = ro(str, "_backend", motionChanged)        # rhi | software
    route = ro(str, "_route", routeChanged)
    routePayload = ro("QVariantMap", "_route_payload", routeChanged)
    iconFamily = ro(str, "_icon_family")

    @Property(float, notify=motionChanged)
    def k(self) -> float:
        """Duration scale: QML writes ``duration: app.ui.k * 220``."""
        return MO.K.get(self._motion, 0.6)

    @Property(int, notify=motionChanged)
    def dockMeasureMs(self) -> int:  # noqa: N802
        """The guard's window for one dock opening: the grow and a frame or two (``motion.dock_measure_ms``)."""
        return MO.dock_measure_ms(self._motion)

    @Property(bool, notify=motionChanged)
    def ambient(self) -> bool:
        """Ambient loops allowed (rich only; QML also gates on the window being active)."""
        return self._motion == "rich"

    @Property(str, notify=motionChanged)
    def motionSetting(self) -> str:  # noqa: N802
        return self.app.ctx.settings.motion if self.app.ctx.settings.motion in MO.SETTINGS else "auto"

    @Property(str, notify=motionChanged)
    def motionReason(self) -> str:  # noqa: N802
        """One finding line for Settings > Appearance."""
        s, f = self.app.ctx.settings, self._facts
        word = {"rich": "Rich", "purposeful": "Purposeful", "off": "Off"}[self._motion]
        if s.motion in MO.LEVELS:
            return f"{word}, your choice"
        if s.motion_reduced_to in MO.LEVELS and s.motion_reduced_to == self._motion \
                and MO.auto_level(f, self._backend) != self._motion:
            return f"{word}, reduced on this PC after dropped frames"
        render = "software rendering" if self._backend == "software" else "the graphics card"
        facts = [render, f"a {f.screen_w} × {f.screen_h} screen"]
        if f.remote_session:
            facts = ["a remote desktop session"]
        elif f.animations_off:
            facts.append("Windows animations off")
        elif f.on_battery:
            facts.append("battery power")
        return f"{word}, chosen for {' and '.join(facts)}"

    @Property(int, constant=True)
    def minimumWidth(self) -> int:  # noqa: N802
        return MIN_W

    @Property(int, constant=True)
    def minimumHeight(self) -> int:  # noqa: N802
        return MIN_H

    @Property(str, constant=True)
    def appIcon(self) -> str:  # noqa: N802
        """File URL of the app mark (the rail)."""
        from PySide6.QtCore import QUrl

        from project_opener import constants as C
        return QUrl.fromLocalFile(str(C.resource_path("icon") / "app-64.png")).toString()

    @Property(int, constant=True)
    def railWidth(self) -> int:  # noqa: N802
        return RAIL_W

    @Property(bool, notify=routeChanged)
    def canGoBack(self) -> bool:  # noqa: N802
        return bool(self._history)

    # ------------------------------------------------------------- slots
    @Slot(str, "QVariantMap")
    def go(self, route: str, payload: dict[str, Any] | None = None) -> None:
        if route not in ROUTES:
            log.warning("unknown route %s", route)
            return
        payload = dict(payload or {})
        if (route, payload) == (self._route, self._route_payload):
            return
        self._history.append((self._route, self._route_payload))
        del self._history[:-20]
        self._route, self._route_payload = route, payload
        self.routeChanged.emit()

    @Slot()
    def back(self) -> None:
        if not self._history:
            self.go("home", {})
            return
        self._route, self._route_payload = self._history.pop()
        self.routeChanged.emit()

    @Slot(str, result=str)
    def glyph(self, name: str) -> str:
        """The Phosphor character for ``name`` ("house", "ph.house", "fa5s.ship"); "" when unknown."""
        _, cmap = phosphor()
        code = cmap.get(icon_name(name, ""), 0) if cmap else 0
        return chr(code) if code else ""

    @Slot(str)
    def setMotion(self, level: str) -> None:  # noqa: N802
        """Settings > Appearance: auto | rich | purposeful | off.  Choosing resets the guard's reduction."""
        if level not in MO.SETTINGS:
            return
        s = self.app.ctx.settings
        s.motion = level
        s.motion_reduced_to = ""
        s.save()
        self._guard = MO.RuntimeGuard()
        self._motion = MO.resolve_motion(s.motion, "", self._facts, self._backend)
        self.motionChanged.emit()

    @Slot(float, float)
    def reportDockFrames(self, mean_ms: float, worst1_ms: float) -> None:  # noqa: N802
        """Each dock opening; two slow ones in a row drop a level (``auto`` only), saved and said once."""
        s = self.app.ctx.settings
        drop = self._guard.report(self._motion, mean_ms, worst1_ms)
        log.info("dock frames: mean %.1f ms, worst 1%% %.1f ms (%s)", mean_ms, worst1_ms, self._motion)
        if not drop or s.motion in MO.LEVELS:
            return
        s.motion_reduced_to = drop
        s.save()
        self._motion = drop
        self.motionChanged.emit()
        self.motionReduced.emit(MO.REDUCED_MESSAGE)
        self.app.toast.emit("Motion reduced", MO.REDUCED_MESSAGE, "info")

    @Slot()
    def beginDockMeasure(self) -> None:  # noqa: N802
        self._stamps = [time.perf_counter()]

    @Slot()
    def endDockMeasure(self) -> None:  # noqa: N802
        stamps, self._stamps = self._stamps, None
        if not stamps or self._motion == "off":
            return
        stamps = MO.window_stamps(stamps, MO.dock_measure_ms(self._motion))   # the timer may fire late
        if len(stamps) < 4:
            return
        mean, worst = MO.guard_stats(stamps)     # the grow's frames, not the click-to-first-frame time
        self.reportDockFrames(mean, worst)

    @Slot(str)
    def setTheme(self, mode: str) -> None:  # noqa: N802
        """dark | light | system: rebuild tokens."""
        if mode not in ("dark", "light", "system"):
            return
        s = self.app.ctx.settings
        s.theme = mode
        s.save()
        self._theme_mode = mode
        self.retheme()

    def retheme(self) -> None:
        s = self.app.ctx.settings
        self._dark = resolve_dark(self._theme_mode)
        self._tokens = tokens_for(self._dark, s.accent, s.density)
        self.tokensChanged.emit()
        if self._window is not None:
            try:
                from project_opener.core import winutil
                winutil.apply_dark_title_bar(int(self._window.winId()), self._dark)
            except Exception:  # noqa: BLE001
                pass

    # ----------------------------------------------------------- palette
    @Property(QObject, constant=True)
    def palette(self) -> DictListModel:
        """The command palette's rows: grey headings (Activities, Projects, Items, Actions) and hits."""
        return self._palette

    @Slot(str)
    def setPaletteQuery(self, query: str) -> None:  # noqa: N802
        self._palette_query = query
        self._palette.reset(self.palette_rows(query))
        self.paletteChanged.emit()

    def palette_rows(self, query: str) -> list[dict[str, Any]]:
        store = self.app.ctx.store
        q = query.strip().lower()
        rows: list[dict[str, Any]] = []

        def group(name: str, hits: list[dict[str, Any]]) -> None:
            if not hits:
                return
            rows.append({"rowKey": f"h:{name}", "rowKind": "heading", "group": name, "title": name, "subtitle": "",
                         "glyph": "", "dotColor": "", "shortcut": "", "action": "", "target": ""})
            rows.extend(hits[:PALETTE_LIMIT])

        projects = {p.id: p for p in store.projects}
        acts = []
        for a in store.sorted_activities():
            spine = projects[a.primary_project_id].spine if a.primary_project_id in projects else ""
            title = T.activity_title(a.name, spine)
            if q and q not in (title + " " + a.search_blob()).lower():
                continue
            color = a.color or (projects[a.primary_project_id].color if a.primary_project_id in projects else "")
            acts.append({"rowKey": f"a:{a.id}", "rowKind": "hit", "group": "Activities", "title": title,
                         "subtitle": T.plural(len(a.items), "item"), "glyph": icon_name(a.icon),
                         "dotColor": color, "shortcut": "", "action": "openActivityPage", "target": a.id})
        projs = []
        for p in store.sorted_projects():
            if q and q not in (p.title + " " + p.search_blob()).lower():
                continue
            projs.append({"rowKey": f"p:{p.id}", "rowKind": "hit", "group": "Projects", "title": p.title,
                          "subtitle": T.subtitle_line(p), "glyph": icon_name(p.icon, DEFAULT_PROJECT_ICON),
                          "dotColor": p.color, "shortcut": "", "action": "openProjectPage", "target": p.id})
        items = []
        if q:
            for p in store.projects:
                for it in p.items:
                    if q in (it.display_name + " " + it.path).lower():
                        items.append({"rowKey": f"i:{p.id}:{it.id}", "rowKind": "hit", "group": "Items",
                                      "title": it.display_name, "subtitle": f"{p.title} · {it.path}",
                                      "glyph": KIND_GLYPHS.get(it.kind, "file"), "dotColor": "", "shortcut": "",
                                      "action": "openItem", "target": f"{p.id}|{it.id}"})
        actions = []
        for title, glyph, action, shortcut in ACTIONS:
            if q and q not in title.lower():
                continue
            actions.append({"rowKey": f"x:{action}", "rowKind": "hit", "group": "Actions", "title": title,
                            "subtitle": "", "glyph": glyph, "dotColor": "", "shortcut": shortcut, "action": action,
                            "target": ""})
        group("Activities", acts)
        group("Projects", projs)
        group("Items", items)
        group("Actions", actions)
        return rows


KIND_GLYPHS = {"file": "file", "folder": "folder", "url": "link", "app": "app-window", "command": "terminal"}
ACTIONS = (
    ("New activity", "plus", "newActivity", "Ctrl+N"),
    ("Start from what's open", "browsers", "startFromOpen", ""),
    ("Snapshot now", "camera", "snapshotNow", "Ctrl+Alt+S"),
    ("Add a window", "selection-plus", "addWindow", "Ctrl+Alt+A"),
    ("New project", "folder-plus", "newProject", ""),
    ("New task", "check-square", "newTask", ""),
    ("Go to Home", "house", "goHome", ""),
    ("Go to Activities", "stack", "goActivities", ""),
    ("Go to Projects", "squares-four", "goProjects", ""),
    ("Go to Team Hub", "users-three", "goHub", ""),
    ("Check for updates", "arrow-circle-down", "goUpdates", ""),
    ("Settings", "sliders-horizontal", "goSettings", "Ctrl+,"),
    ("Switch light or dark", "circle-half", "toggleTheme", ""),
)
