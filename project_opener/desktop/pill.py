"""The pill and its panel: a separate focus-less QQuickWindow.  Owner: builder 3 (DESKTOP).

Window: ``Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint | WindowDoesNotAcceptFocus``,
then natively ``WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW`` (never in Alt+Tab, never takes focus).
The capture engine excludes this process's windows, so the pill is never in its own captures.
Position: one per monitor layout (``layout_key``), snapped to the nearest edge; default
bottom-right above the notification area.  QML: ``qml/desktop/Pill.qml`` (+ ``PillPanel.qml``),
context properties ``app`` (the facade) and ``pill`` (this controller).

Geometry is in Qt's logical coordinates; Qt 6 keeps each screen's origin at its native position
and scales sizes per monitor, so the work area (``QScreen.availableGeometry``) and the window
geometry share one coordinate system and per-monitor DPI needs nothing extra here.

The window is only as large as what it shows: the capsule (or the 6 px edge tab) at rest, the
panel's rectangle while the panel is open, so the transparent remainder never blocks a click.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QRect, QTimer, QUrl, Signal, Slot

log = logging.getLogger(__name__)

EDGES = ("bottom", "top", "left", "right")
GAP = 12                    # space between the capsule and the work-area edge
CORNER = 2                  # along its edge the pill keeps GAP + CORNER from a corner, so it is
                            # always nearer its own edge than the neighbouring one (stable re-snap)
DEFAULT_INSET = 24          # default: this far from the right end of the bottom edge
CAPSULE_H = 30
EDGE_TAB = (6, 64)          # thickness, length
HOVER_OPEN_MS = 500
LEAVE_CLOSE_MS = 400
SAVED_FLASH_MS = 2000
PANEL_GROW_MS = 180

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000

Work = tuple[int, int, int, int]       # left, top, right, bottom (exclusive)


def layout_key(monitors: list[dict[str, Any]]) -> str:
    """A stable key for the current monitor arrangement: sorted "device@x,y,w,h" joined by "|"."""
    parts = sorted(f"{m.get('device', '')}@{','.join(str(v) for v in m.get('rect', []))}" for m in monitors)
    return "|".join(parts)


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if hi < lo else max(lo, min(hi, v))


def snap_to_edge(x: int, y: int, w: int, h: int, work: Work) -> tuple[str, int]:
    """(edge, offset along it) for a pill dropped at (x, y) inside work area ``work`` (l, t, r, b).

    The edge is the one the pill is nearest to.  The offset anchors the pill to the nearer end of
    that edge, so a label that grows (``Saved · 12 things · 14:32``) grows away from that end:
    positive = from the start (left or top) to the pill's near side; negative = minus the distance
    from the end (right or bottom) to the pill's far side.  Never 0: a corner inset is kept.
    """
    left, top, right, bottom = work
    x = _clamp(x, left, right - w)            # a drop past the work area counts as at its edge
    y = _clamp(y, top, bottom - h)
    dist = {"left": x - left, "right": right - (x + w), "top": y - top, "bottom": bottom - (y + h)}
    edge = min(EDGES, key=lambda e: (dist[e], EDGES.index(e)))   # ties: bottom, top, left, right
    inset = GAP + CORNER
    if edge in ("top", "bottom"):
        start, end, pos, size = left, right, x, w
    else:
        start, end, pos, size = top, bottom, y, h
    if pos + size / 2 <= (start + end) / 2:
        return edge, int(round(max(inset, pos - start)))
    return edge, -int(round(max(inset, end - (pos + size))))


def place_on_edge(edge: str, offset: int, w: int, h: int, work: Work, gap: int = GAP) -> tuple[int, int]:
    """Top-left of a w x h window at ``offset`` along ``edge`` (see ``snap_to_edge``), ``gap`` from it."""
    left, top, right, bottom = work
    inset = gap + CORNER
    if edge in ("top", "bottom"):
        x = left + offset if offset >= 0 else right + offset - w
        x = _clamp(x, left + inset, right - w - inset)
        y = top + gap if edge == "top" else bottom - h - gap
    else:
        y = top + offset if offset >= 0 else bottom + offset - h
        y = _clamp(y, top + inset, bottom - h - inset)
        x = left + gap if edge == "left" else right - w - gap
    return int(round(x)), int(round(y))


def default_place(w: int, work: Work) -> tuple[str, int]:
    """Bottom-right, just above the notification area."""
    return "bottom", -DEFAULT_INSET


def edge_tab_size(edge: str) -> tuple[int, int]:
    thick, length = EDGE_TAB
    return (thick, length) if edge in ("left", "right") else (length, thick)


def panel_rect(edge: str, anchor: tuple[int, int, int, int], pw: int, ph: int, work: Work) -> tuple[int, int]:
    """Top-left of the panel opening from the pill at ``anchor`` (x, y, w, h), away from its edge.

    Bottom edge: upward, sharing the pill's bottom; top: downward; left/right: sideways, sharing the
    pill's outer side.  Along the edge it lines up with the pill's nearer end and stays in ``work``.
    """
    left, top, right, bottom = work
    ax, ay, aw, ah = anchor
    if edge in ("top", "bottom"):
        in_right_half = ax + aw / 2 > (left + right) / 2
        x = ax + aw - pw if in_right_half else ax
        y = ay + ah - ph if edge == "bottom" else ay
    else:
        in_lower_half = ay + ah / 2 > (top + bottom) / 2
        y = ay + ah - ph if in_lower_half else ay
        x = ax if edge == "left" else ax + aw - pw
    return int(_clamp(x, left, right - pw)), int(_clamp(y, top, bottom - ph))


def grow_origin(edge: str, anchor: tuple[int, int, int, int], panel: tuple[int, int, int, int]) -> str:
    """Which corner of the panel the pill sits in ("bottomright", "topleft", ...), for the grow motion."""
    ax, ay, aw, ah = anchor
    px, py, pw, ph = panel
    vert = "bottom" if ay + ah / 2 > py + ph / 2 else "top"
    horiz = "right" if ax + aw / 2 > px + pw / 2 else "left"
    return vert + horiz


# ------------------------------------------------------------ the states
@dataclass(frozen=True)
class PillFacts:
    state: str = "idle"              # app.capture.state: idle | running | needs | paused | saved
    label: str = ""                  # app.capture.runningLabel
    color: str = ""                  # app.capture.runningColor
    open_count: int = 0
    needs_path: int = 0
    drive_down: bool = False
    saved_text: str = ""             # "12 things · 14:32" from the last checkpointSaved
    saved_flash: bool = False        # inside the 2 s after a checkpoint
    pinned: bool = False             # Settings.pill_pinned
    enabled: bool = True             # Settings.pill_enabled
    quiet: bool = False              # desktop quiet time
    rest_style: str = "pill"         # pill | edge


def things(n: int) -> str:
    return f"{n} thing" if n == 1 else f"{n} things"


def pill_view(f: PillFacts) -> dict[str, Any]:
    """What the pill shows.  Keys: visible, kind (running|needs|paused|saved|start|hidden), dot
    (fill|hollow|muted), ring (""|warn|bad), tone (""|ok), text, detail, edge (edge-tab style), color.
    """
    hidden = {"visible": False, "kind": "hidden", "dot": "fill", "ring": "", "tone": "", "text": "",
              "detail": "", "edge": False, "color": f.color, "reason": ""}
    if not f.enabled:
        return {**hidden, "reason": "turned off"}
    if f.quiet:
        return {**hidden, "reason": "quiet time"}
    edge = f.rest_style == "edge"
    label = f.label or "Activity"
    if f.state == "idle" or f.state not in ("running", "needs", "paused", "saved"):
        if not f.pinned:
            return {**hidden, "reason": "nothing running"}
        return {**hidden, "visible": True, "kind": "start", "dot": "muted", "text": "Start from what's open",
                "edge": edge}
    base = {**hidden, "visible": True, "edge": edge, "text": label}
    if f.saved_flash or f.state == "saved":
        return {**base, "kind": "saved", "tone": "ok", "text": "Saved",
                "detail": f.saved_text or things(f.open_count)}
    if f.state == "paused":
        return {**base, "kind": "paused", "dot": "hollow", "detail": "paused"}
    if f.state == "needs" or f.needs_path > 0 or f.drive_down:
        if f.drive_down:
            return {**base, "kind": "needs", "ring": "bad", "detail": "server offline"}
        n = f.needs_path
        return {**base, "kind": "needs", "ring": "warn",
                "detail": f"{n} needs a path" if n == 1 else f"{n} need a path"}
    return {**base, "kind": "running", "detail": str(f.open_count)}


def panel_meta(open_count: int, identified: int, last_checkpoint: str, since: int) -> str:
    """"12 open · 9 identified · last checkpoint 10:52, 2 new since"."""
    parts = [f"{open_count} open", f"{identified} identified"]
    if last_checkpoint:
        cp = f"last checkpoint {last_checkpoint}"
        if since:
            cp += f", {since} new since"
        parts.append(cp)
    elif since:
        parts.append(f"{since} new since the start")
    return " · ".join(parts)


def set_no_activate(hwnd: int) -> None:
    """Add WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW to ``hwnd`` (SetWindowLongPtrW, GWL_EXSTYLE)."""
    if sys.platform != "win32" or not hwnd:
        return
    u = ctypes.windll.user32
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    style = u.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    new = (style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
    if new != style:
        u.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new)


def screens_monitors() -> list[dict[str, Any]]:
    from PySide6.QtGui import QGuiApplication
    out = []
    for s in QGuiApplication.screens():
        g = s.geometry()
        out.append({"device": s.name(), "rect": [g.x(), g.y(), g.width(), g.height()],
                    "primary": s is QGuiApplication.primaryScreen()})
    return out


def _work_of(screen: Any) -> Work:
    g = screen.availableGeometry()
    return g.x(), g.y(), g.x() + g.width(), g.y() + g.height()


class PillController(QObject):
    """Owns the pill window; QML reads ``pill.view``, ``pill.panelOpen``, ``pill.meta`` ... and calls back."""

    geometryChanged = Signal()
    viewChanged = Signal()
    panelChanged = Signal()
    visibilityChanged = Signal(bool)        # the pill is on screen (for DesktopApi.pillVisible)

    def __init__(self, facade: Any, engine: Any, qml_dir: Path | None = None):
        super().__init__(facade)
        self.facade = facade
        self.engine = engine
        self.qml_dir = qml_dir
        self.window = None          # QQuickWindow from Pill.qml
        self._context = None
        self._component = None
        self._view: dict[str, Any] = pill_view(PillFacts())
        self._meta = ""
        self._panel_open = False
        self._panel_size = (400, 260)
        self._content_size = (160, CAPSULE_H)
        self._edge = "bottom"
        self._offset: int | None = None
        self._screen_name = ""
        self._grow_from = "bottomright"
        self._quiet = False
        self._saved_text = ""
        self._saved_flash = False
        self._hover = False
        self._dragging = False
        self._shown = False
        self._hover_timer = QTimer(self, singleShot=True, interval=HOVER_OPEN_MS)
        self._hover_timer.timeout.connect(self._hover_open)
        self._leave_timer = QTimer(self, singleShot=True, interval=LEAVE_CLOSE_MS)
        self._leave_timer.timeout.connect(self.closePanel)
        self._saved_timer = QTimer(self, singleShot=True, interval=SAVED_FLASH_MS)
        self._saved_timer.timeout.connect(self._saved_over)
        self._shrink_timer = QTimer(self, singleShot=True)
        self._shrink_timer.timeout.connect(self._apply_geometry)
        cap = getattr(facade, "capture", None)
        if cap is not None:
            for sig in ("stateChanged", "liveChanged", "checkpointsChanged"):
                if hasattr(cap, sig):
                    getattr(cap, sig).connect(self.refresh)
            if hasattr(cap, "checkpointSaved"):
                cap.checkpointSaved.connect(self._on_checkpoint_saved)

    # ------------------------------------------------------- QML properties
    @Property("QVariantMap", notify=viewChanged)
    def view(self) -> dict[str, Any]:
        return self._view

    @Property(str, notify=viewChanged)
    def meta(self) -> str:
        return self._meta

    @Property(bool, notify=panelChanged)
    def panelOpen(self) -> bool:  # noqa: N802
        return self._panel_open

    @Property(str, notify=geometryChanged)
    def edge(self) -> str:
        return self._edge

    @Property(str, notify=panelChanged)
    def growFrom(self) -> str:  # noqa: N802
        return self._grow_from

    @property
    def visible(self) -> bool:
        return bool(self._view.get("visible"))

    # ---------------------------------------------------------- settings
    @property
    def settings(self) -> Any:
        return self.facade.ctx.settings

    def _facts(self) -> PillFacts:
        cap = getattr(self.facade, "capture", None)

        def g(name: str, default: Any) -> Any:
            if cap is None:
                return default
            v = cap.property(name)
            return default if v is None else v

        s = self.settings
        return PillFacts(
            state=str(g("state", "idle")), label=str(g("runningLabel", "") or g("runningName", "")),
            color=str(g("runningColor", "")), open_count=int(g("openCount", 0)),
            needs_path=int(g("needsPathCount", 0)), drive_down=bool(g("driveDown", False)),
            saved_text=self._saved_text, saved_flash=self._saved_flash,
            pinned=bool(getattr(s, "pill_pinned", False)), enabled=bool(getattr(s, "pill_enabled", True)),
            quiet=self._quiet, rest_style=str(getattr(s, "pill_rest_style", "pill") or "pill"))

    def would_show(self) -> bool:
        """Visible if it were not quiet time (the quiet-time watcher runs only while this is true)."""
        from dataclasses import replace
        return bool(pill_view(replace(self._facts(), quiet=False))["visible"])

    # ------------------------------------------------------------ refresh
    @Slot()
    def refresh(self) -> None:
        view = pill_view(self._facts())
        cap = getattr(self.facade, "capture", None)
        meta = ""
        if cap is not None:
            meta = panel_meta(int(cap.property("openCount") or 0), int(cap.property("identifiedCount") or 0),
                              str(cap.property("lastCheckpointText") or ""), int(cap.property("sinceCheckpoint") or 0))
        changed = view != self._view or meta != self._meta
        was_visible = self.visible
        self._view, self._meta = view, meta
        if changed:
            self.viewChanged.emit()
        if not view["visible"] or view["kind"] == "start":
            if self._panel_open:
                self._set_panel(False)
        if self.window is not None:
            if view["visible"]:
                self._apply_geometry()
                if not self.window.isVisible():
                    self.window.show()
                    set_no_activate(int(self.window.winId()))
            elif self.window.isVisible():
                self.window.hide()
        if was_visible != view["visible"]:
            self.visibilityChanged.emit(bool(view["visible"]))

    def set_quiet(self, quiet: bool) -> None:
        if quiet != self._quiet:
            self._quiet = quiet
            self.refresh()

    def _on_checkpoint_saved(self, _cid: str, count: int, time_text: str) -> None:
        self._saved_text = f"{things(int(count))} · {time_text}" if time_text else things(int(count))
        self._saved_flash = True
        self._saved_timer.start()
        self.refresh()

    def _saved_over(self) -> None:
        self._saved_flash = False
        self.refresh()

    # ------------------------------------------------------------- window
    def create(self) -> None:
        if self.window is not None or self.engine is None or self.qml_dir is None:
            return
        from PySide6.QtQml import QQmlComponent, QQmlContext, QQmlEngine
        self._context = QQmlContext(self.engine.rootContext(), self)
        self._context.setContextProperty("pill", self)
        comp = QQmlComponent(self.engine, QUrl.fromLocalFile(str(self.qml_dir / "desktop" / "Pill.qml")))
        win = comp.create(self._context)
        if win is None:
            log.error("Pill.qml failed: %s", comp.errorString())
            return
        # PySide ties the created object's life to the component's wrapper: keep both.
        self._component = comp
        QQmlEngine.setObjectOwnership(win, QQmlEngine.ObjectOwnership.CppOwnership)
        self.window = win
        self._restore_position()
        win.winId()                                  # create the native window now, then restyle it
        set_no_activate(int(win.winId()))
        win.screenChanged.connect(lambda *_: self._apply_geometry())
        self.refresh()

    @Slot()
    def show(self) -> None:
        if self.window is None:
            self.create()
        self.refresh()

    @Slot()
    def hide(self) -> None:
        self._set_panel(False)
        if self.window is not None:
            self.window.hide()

    def destroy(self) -> None:
        self.save_position()
        if self.window is not None:
            self.window.hide()
            self.window.deleteLater()
            self.window = None

    def _screen(self) -> Any:
        from PySide6.QtGui import QGuiApplication
        for s in QGuiApplication.screens():
            if s.name() == self._screen_name:
                return s
        return QGuiApplication.primaryScreen()

    def _rest_size(self) -> tuple[int, int]:
        if self._view.get("edge"):
            return edge_tab_size(self._edge)
        w, h = self._content_size
        return max(40, int(w)), max(CAPSULE_H, int(h))

    def _anchor(self) -> tuple[int, int, int, int]:
        screen = self._screen()
        if screen is None:
            return 0, 0, *self._rest_size()
        work = _work_of(screen)
        w, h = self._rest_size()
        if self._offset is None:
            self._edge, self._offset = default_place(w, work)
        gap = 0 if self._view.get("edge") else GAP
        x, y = place_on_edge(self._edge, self._offset, w, h, work, gap)
        return x, y, w, h

    @Slot()
    def _apply_geometry(self) -> None:
        if self.window is None or self._dragging:
            return
        ax, ay, aw, ah = self._anchor()
        if self._panel_open:
            pw, ph = self._panel_size
            px, py = panel_rect(self._edge, (ax, ay, aw, ah), pw, ph, _work_of(self._screen()))
            grow = grow_origin(self._edge, (ax, ay, aw, ah), (px, py, pw, ph))
            if grow != self._grow_from:
                self._grow_from = grow
                self.panelChanged.emit()
            rect = QRect(px, py, pw, ph)
        else:
            rect = QRect(ax, ay, aw, ah)
        if self.window.geometry() != rect:
            self.window.setGeometry(rect)
            self.geometryChanged.emit()

    def _restore_position(self) -> None:
        saved = (getattr(self.settings, "pill_positions", {}) or {}).get(layout_key(screens_monitors()))
        if isinstance(saved, dict) and saved.get("edge") in EDGES:
            self._edge = str(saved["edge"])
            try:
                self._offset = int(saved.get("offset"))
            except (TypeError, ValueError):
                self._offset = None
            self._screen_name = str(saved.get("monitor", ""))
        else:
            self._offset = None
            self._screen_name = ""

    def save_position(self) -> None:
        if self._offset is None:
            return
        s = self.settings
        positions = dict(getattr(s, "pill_positions", {}) or {})
        positions[layout_key(screens_monitors())] = {"edge": self._edge, "offset": int(self._offset),
                                                     "monitor": self._screen().name() if self._screen() else ""}
        s.pill_positions = positions
        try:
            s.save()
        except Exception:  # noqa: BLE001
            log.exception("could not save the pill position")

    def screens_changed(self) -> None:
        """A monitor was added/removed/changed: take the position saved for the new layout."""
        self._restore_position()
        self._apply_geometry()

    # --------------------------------------------------------- QML calls
    @Slot(float, float)
    def setContentSize(self, w: float, h: float) -> None:  # noqa: N802
        size = (int(round(w)), int(round(h)))
        if size != self._content_size and w > 0 and h > 0:
            self._content_size = size
            if not self._panel_open:
                self._apply_geometry()

    @Slot(float, float)
    def setPanelSize(self, w: float, h: float) -> None:  # noqa: N802
        size = (int(round(w)), int(round(h)))
        if size != self._panel_size and w > 0 and h > 0:
            self._panel_size = size
            if self._panel_open:
                self._apply_geometry()

    @Slot(bool)
    def hoverChanged(self, inside: bool) -> None:  # noqa: N802
        self._hover = inside
        if inside:
            self._leave_timer.stop()
            if not self._panel_open and self._view.get("kind") not in ("start", "hidden"):
                self._hover_timer.start()
        else:
            self._hover_timer.stop()
            if self._panel_open:
                self._leave_timer.start()

    def _hover_open(self) -> None:
        if self._hover and not self._dragging:
            self.openPanel()

    @Slot()
    def clicked(self) -> None:
        if self._view.get("kind") == "start":
            self.act("start_from_open")
        else:
            self.togglePanel()

    @Slot(float, float)
    def dragTo(self, x: float, y: float) -> None:  # noqa: N802
        """While dragging: the window follows the pointer (top-left in global logical coordinates)."""
        if self.window is None:
            return
        self._dragging = True
        self._hover_timer.stop()
        if self._panel_open:
            self._set_panel(False)
            w, h = self._rest_size()
            self.window.setGeometry(QRect(int(x), int(y), w, h))
        self.window.setPosition(int(x), int(y))

    @Slot(int, int)
    def dropped(self, x: int, y: int) -> None:
        """The user dragged the pill and let go: snap, save per layout."""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QGuiApplication
        self._dragging = False
        w, h = self._rest_size()
        screen = QGuiApplication.screenAt(QPoint(int(x + w / 2), int(y + h / 2))) or self._screen()
        if screen is None:
            return
        self._screen_name = screen.name()
        edge, offset = snap_to_edge(int(x), int(y), w, h, _work_of(screen))
        self._edge, self._offset = edge, offset
        self.geometryChanged.emit()
        self._apply_geometry()
        self.save_position()

    # ------------------------------------------------------------- panel
    def _set_panel(self, on: bool) -> None:
        if on == self._panel_open:
            return
        self._panel_open = on
        if on:
            self._shrink_timer.stop()
            self._apply_geometry()
        else:
            # Keep the panel's size while it closes (rich/purposeful), then shrink back to the capsule.
            k = float(self.facade.ui.property("k") or 0) if getattr(self.facade, "ui", None) else 0.0
            self._shrink_timer.start(max(0, int(PANEL_GROW_MS * k)))
        self.panelChanged.emit()

    @Slot()
    def openPanel(self) -> None:  # noqa: N802
        if not self.visible or self._view.get("kind") == "start":
            return
        self._set_panel(True)

    @Slot()
    def closePanel(self) -> None:  # noqa: N802
        self._set_panel(False)

    @Slot()
    def togglePanel(self) -> None:  # noqa: N802
        if self._panel_open:
            self.closePanel()
        else:
            self.openPanel()

    @Slot(str)
    def act(self, action: str) -> None:
        """The panel's buttons.  A failing capture call is logged, never raised into QML."""
        f = self.facade
        try:
            if action == "snapshot":
                f.capture.snapshotNow()
            elif action == "save_new":
                f.capture.saveNewAsItems()
            elif action == "add_window":
                self.closePanel()
                if f.desktop is not None:
                    f.desktop.startPicker()
            elif action == "pause":
                f.capture.pause()
            elif action == "resume":
                f.capture.resume()
            elif action in ("review", "open"):
                self.closePanel()
                rid = str(f.capture.property("runningId") or "")
                if rid:
                    payload = {"activityId": rid}
                    if action == "review":
                        payload["focus"] = "unidentified"
                    f.ui.go("activity", payload)
                f.showWindowRequested.emit()
            elif action == "start_from_open":
                f.handle_command({"cmd": "start-from-open"})
            else:
                log.warning("pill: unknown action %s", action)
        except Exception:  # noqa: BLE001
            log.exception("pill: %s failed", action)
