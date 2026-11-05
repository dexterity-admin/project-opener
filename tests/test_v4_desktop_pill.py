"""The pill's state machine, edge snapping and placement per monitor (builder 3).  Pure functions."""
import pytest

from project_opener.desktop import pill as P

FHD = (0, 0, 1920, 1040)                     # 1920x1080 with a 40 px taskbar at the bottom
RIGHT = (1920, 0, 3200, 984)                 # a 1280x1024 monitor to the right (logical), taskbar 40
TALL_LEFT = (-1080, -400, 0, 1520)           # a portrait monitor left of the primary, origin negative


# ------------------------------------------------------------------ snapping
@pytest.mark.parametrize(("x", "y", "edge"), [
    (900, 1000, "bottom"), (900, 5, "top"), (3, 500, "left"), (1900, 500, "right"),
    (1700, 990, "bottom"),          # the default corner: nearer the bottom than the right
])
def test_snap_picks_nearest_edge(x, y, edge):
    assert P.snap_to_edge(x, y, 150, 30, FHD)[0] == edge


def test_snap_offset_anchors_to_the_nearer_end():
    assert P.snap_to_edge(300, 1000, 150, 30, FHD) == ("bottom", 300)          # from the left end
    assert P.snap_to_edge(900, 1000, 150, 30, FHD) == ("bottom", -870)         # from the right end
    assert P.snap_to_edge(-50, 1030, 150, 30, FHD) == ("bottom", 14)           # past the corner: kept off it
    assert P.snap_to_edge(1900, 1030, 150, 30, FHD) == ("bottom", -14)
    assert P.snap_to_edge(1900, 300, 150, 30, FHD) == ("right", 300)


def test_snap_on_other_monitors_is_relative_to_their_work_area():
    assert P.snap_to_edge(1930, 600, 150, 30, RIGHT) == ("left", -354)
    edge, off = P.snap_to_edge(-1070, 1480, 150, 30, TALL_LEFT)
    assert (edge, off) == ("bottom", 14)
    x, y = P.place_on_edge(edge, off, 150, 30, TALL_LEFT)
    assert x == -1080 + 14 and y == 1520 - 30 - P.GAP


@pytest.mark.parametrize("work", [FHD, RIGHT, TALL_LEFT])
@pytest.mark.parametrize(("x", "y"), [(10, 10), (500, 500), (1800, 1000), (-900, 1400), (2500, 900)])
def test_snap_then_place_stays_inside_and_on_the_edge(work, x, y):
    w, h = 160, 30
    edge, off = P.snap_to_edge(x, y, w, h, work)
    px, py = P.place_on_edge(edge, off, w, h, work)
    left, top, right, bottom = work
    assert left <= px and px + w <= right and top <= py and py + h <= bottom
    gap = {"left": px - left, "right": right - (px + w), "top": py - top, "bottom": bottom - (py + h)}[edge]
    assert gap == P.GAP
    # snapping the placed pill again is stable
    assert P.snap_to_edge(px, py, w, h, work) == (edge, off)


def test_default_place_is_bottom_right_above_the_clock():
    edge, off = P.default_place(150, FHD)
    x, y = P.place_on_edge(edge, off, 150, 30, FHD)
    assert edge == "bottom" and x + 150 == 1920 - P.DEFAULT_INSET and y == 1040 - 30 - P.GAP


def test_width_change_keeps_the_anchored_end_still():
    edge, off = P.default_place(150, FHD)
    x1, _ = P.place_on_edge(edge, off, 150, 30, FHD)
    x2, _ = P.place_on_edge(edge, off, 320, 30, FHD)      # "Saved 12 things · 14:32" is wider
    assert x1 + 150 == x2 + 320                           # grows leftward from the right end
    x1, _ = P.place_on_edge("bottom", 300, 150, 30, FHD)
    x2, _ = P.place_on_edge("bottom", 300, 320, 30, FHD)
    assert x1 == x2 == 300                                # a left-anchored pill grows rightward


def test_edge_tab_is_flush():
    w, h = P.edge_tab_size("right")
    assert (w, h) == (6, 64)
    x, _ = P.place_on_edge("right", 500, w, h, FHD, gap=0)
    assert x + w == 1920
    assert P.edge_tab_size("bottom") == (64, 6)


# --------------------------------------------------------------------- panel
def test_panel_opens_upward_from_bottom_right():
    anchor = (1700, 980, 180, 30)
    x, y = P.panel_rect("bottom", anchor, 400, 260, FHD)
    assert (x + 400, y + 260) == (1880, 1010)              # shares the pill's right and bottom
    assert P.grow_origin("bottom", anchor, (x, y, 400, 260)) == "bottomright"


def test_panel_from_top_left_and_sides_stays_inside():
    x, y = P.panel_rect("top", (40, 12, 150, 30), 400, 260, FHD)
    assert (x, y) == (40, 12)
    x, y = P.panel_rect("left", (12, 900, 150, 30), 400, 260, FHD)
    assert x == 12 and y + 260 == 930
    x, y = P.panel_rect("right", (1758, 10, 150, 30), 400, 260, FHD)
    assert x + 400 == 1908 and y == 10
    x, y = P.panel_rect("bottom", (0, 1000, 60, 30), 400, 900, (0, 0, 1366, 728))   # too tall: clamped
    assert y == 0 and x == 0


def test_layout_key_is_order_independent():
    a = [{"device": r"\.\DISPLAY1", "rect": [0, 0, 1920, 1080]}, {"device": r"\.\DISPLAY2", "rect": [1920, 0, 1280, 1024]}]
    assert P.layout_key(a) == P.layout_key(list(reversed(a)))
    assert P.layout_key(a) != P.layout_key(a[:1])


# ------------------------------------------------------------- state machine
def view(**kw):
    return P.pill_view(P.PillFacts(**kw))


def test_running():
    v = view(state="running", label="Lot 7 check", color="#4F7DFF", open_count=12)
    assert v["visible"] and v["kind"] == "running" and v["dot"] == "fill" and v["ring"] == ""
    assert (v["text"], v["detail"], v["color"]) == ("Lot 7 check", "12", "#4F7DFF")


def test_needs_amber_and_red():
    v = view(state="needs", label="Lot 7 check", needs_path=3)
    assert (v["kind"], v["ring"], v["detail"]) == ("needs", "warn", "3 need a path")
    assert view(state="needs", needs_path=1)["detail"] == "1 needs a path"
    v = view(state="needs", needs_path=3, drive_down=True)
    assert (v["ring"], v["detail"]) == ("bad", "Server offline")
    assert view(state="running", needs_path=2)["ring"] == "warn"     # counts win over a stale state


def test_paused_saved_and_back():
    assert view(state="paused", label="L")["dot"] == "hollow"
    assert view(state="paused", label="L")["detail"] == "paused"
    v = view(state="running", label="L", saved_flash=True, saved_text="12 things · 14:32")
    assert (v["kind"], v["tone"], v["text"], v["detail"]) == ("saved", "ok", "Saved", "12 things · 14:32")
    assert view(state="saved", open_count=1)["detail"] == "1 thing"
    assert view(state="running", label="L", saved_flash=False)["kind"] == "running"


def test_idle_hidden_unless_pinned():
    assert view(state="idle")["visible"] is False
    v = view(state="idle", pinned=True)
    assert v["visible"] and v["kind"] == "start" and v["text"] == "Start from what's open" and v["dot"] == "muted"


def test_hidden_when_off_or_quiet():
    assert view(state="running", enabled=False)["visible"] is False
    assert view(state="running", quiet=True)["reason"] == "quiet time"
    assert view(state="idle", pinned=True, quiet=True)["visible"] is False


def test_edge_rest_style():
    assert view(state="running", rest_style="edge")["edge"] is True
    assert view(state="running")["edge"] is False


def test_panel_meta():
    assert P.panel_meta(12, 9, "10:52", 2) == "12 open · 9 identified · last checkpoint 10:52, 2 new since"
    assert P.panel_meta(3, 3, "", 0) == "3 open · 3 identified"
    assert P.panel_meta(3, 1, "09:00", 0) == "3 open · 1 identified · last checkpoint 09:00"
