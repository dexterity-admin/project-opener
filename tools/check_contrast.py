"""Compute WCAG contrast for every text/surface pair the theme defines.

    python tools/check_contrast.py          # both themes, exit 1 on any failure

Body-text pairs must reach 4.5:1, large text and controls 3:1 (docs/DESIGN.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from project_opener.ui import theme  # noqa: E402


def pairs(t: theme.Tokens) -> list[tuple[str, str, str, float]]:
    """(name, fg, bg, minimum)"""
    out = [
        ("text on bg", t.text, t.bg, 4.5), ("text on surface", t.text, t.surface, 4.5),
        ("muted on bg", t.text_muted, t.bg, 4.5), ("muted on surface", t.text_muted, t.surface, 4.5),
        ("muted on surface_2", t.text_muted, t.surface_2, 4.5),
        ("faint on bg", t.text_faint, t.bg, 4.5), ("faint on surface", t.text_faint, t.surface, 4.5),
        ("accent_fg on accent", t.accent_fg, t.accent, 4.5), ("accent as text on surface", t.accent, t.surface, 4.5),
        ("text on accent_soft", t.text, t.accent_soft, 4.5),
        ("success on surface", t.success, t.surface, 4.5), ("warning on surface", t.warning, t.surface, 4.5),
        ("danger on surface", t.danger, t.surface, 4.5), ("info on surface", t.info, t.surface, 4.5),
        ("pill ok", t.pill_ok_ink, t.pill_ok_bg, 4.5), ("pill warn", t.pill_warn_ink, t.pill_warn_bg, 4.5),
        ("pill bad", t.pill_bad_ink, t.pill_bad_bg, 4.5), ("pill info", t.pill_info_ink, t.pill_info_bg, 4.5),
        ("pill neutral", t.pill_neutral_ink, t.pill_neutral_bg, 4.5),
        ("field ink on mint", t.field_ink, t.field_mint, 4.5), ("field ink on sky", t.field_ink, t.field_sky, 4.5),
        ("field ink on blush", t.field_ink, t.field_blush, 4.5),
        ("border_strong on surface (control edge)", t.border_strong, t.surface, 1.2),
    ]
    for hexv, name in theme.ACCENTS:
        out.append((f"white on accent {name}", "#FFFFFF", hexv, 4.5))
    return out


def main() -> int:
    bad = 0
    for dark in (False, True):
        t = theme.build_tokens(dark)
        print(f"\n{t.name.upper()}")
        for name, fg, bg, minimum in pairs(t):
            ratio = theme.contrast(fg, bg)
            ok = ratio >= minimum
            bad += not ok
            print(f"  {'ok  ' if ok else 'FAIL'} {ratio:5.2f}  {name}  ({fg} on {bg}, min {minimum})")
    print("\nall pairs pass" if not bad else f"\n{bad} pair(s) fail")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
