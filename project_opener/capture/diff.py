"""Pure snapshot arithmetic (no Win32, fully unit-testable).  Owner: builder 2.

* ``match_items``: set ``entry.item_id`` for entries whose path equals an activity item's
  resolved path (case-insensitive, trailing separators ignored, drive letter vs UNC through
  the resolver's ``portable`` form).
* ``changed``: whether a new pass differs from the last written snapshot in a way worth
  writing (identified set, statuses or a placement), so the live file is rewritten only on change.
* ``new_since``: entries identified now that were not in the checkpoint ("2 new since").
* ``order_for_restore``: restorable entries in the activity's launch order, unknown ones last.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from project_opener.core import models as M


def norm_path(path: str) -> str:
    return (path or "").strip().rstrip("\\/").lower()


def norm_url(url: str) -> str:
    """URLs compared without scheme case, "www.", a trailing slash or a fragment."""
    u = (url or "").strip()
    if "#" in u:
        u = u.split("#", 1)[0]
    low = u.lower()
    for scheme in ("https://", "http://"):
        if low.startswith(scheme):
            u = u[len(scheme):]
            break
    if u.lower().startswith("www."):
        u = u[4:]
    return u.rstrip("/").lower()


def same_target(a: str, b: str, portable: Callable[[str], str] | None = None) -> bool:
    """Whether two paths/URLs name the same thing (deterministic string rules only)."""
    if not a or not b:
        return False
    if a.lower().startswith(("http://", "https://")) or b.lower().startswith(("http://", "https://")):
        return norm_url(a) == norm_url(b)
    if norm_path(a) == norm_path(b):
        return True
    if portable is not None:
        try:
            return norm_path(portable(a)) == norm_path(portable(b))
        except Exception:  # noqa: BLE001
            return False
    return False


def match_items(snapshot: M.Snapshot, items: list[M.Item],
                portable: Callable[[str], str] | None = None,
                resolve: Callable[[str], str] | None = None) -> M.Snapshot:
    """Set ``item_id`` on identified entries that are one of ``items`` (by resolved path); clear it otherwise.

    ``resolve`` turns an item's stored path (variables, environment) into the real one;
    ``portable`` folds drive letters into UNC so ``U:\\x`` and ``\\\\server\\share\\x`` match."""
    targets: list[tuple[str, str]] = []
    for it in items:
        p = it.path
        if resolve is not None:
            try:
                p = resolve(p) or p
            except Exception:  # noqa: BLE001
                pass
        targets.append((it.id, p))
    for e in snapshot.entries:
        e.item_id = ""
        if not e.identified:
            continue
        for item_id, p in targets:
            if same_target(e.path, p, portable):
                e.item_id = item_id
                break
    return snapshot


def _signature(s: M.Snapshot) -> Counter:
    out: Counter = Counter()
    for e in s.entries:
        pl = e.placement
        place = (pl.show_cmd, tuple(pl.normal_rect), pl.monitor) if pl else None
        out[(e.key, e.status, e.path, e.item_id, tuple(e.candidates), e.note, place)] += 1
    return out


def changed(old: M.Snapshot | None, new: M.Snapshot) -> bool:
    """Worth writing: a different set of things, a status, an item link or a placement.  Z-order,
    hwnds, pids and timestamps alone are not a change."""
    if old is None:
        return True
    if old.activity_id != new.activity_id:
        return True
    return _signature(old) != _signature(new)


def new_since(checkpoint: M.Snapshot | None, now: M.Snapshot) -> list[M.SnapshotEntry]:
    """Identified now and not identified in ``checkpoint`` (every identified entry when there is none)."""
    before = {e.key for e in checkpoint.entries if e.identified} if checkpoint else set()
    seen: set[str] = set()
    out: list[M.SnapshotEntry] = []
    for e in now.entries:
        if e.identified and e.key not in before and e.key not in seen:
            seen.add(e.key)
            out.append(e)
    return out


def order_for_restore(snapshot: M.Snapshot, items: list[M.Item]) -> list[M.SnapshotEntry]:
    """Restorable (identified) entries, one per identity: first those that are items, in the
    activity's launch order; then the rest from the back of the z-order to the front, so the
    window that was in front ends up in front again."""
    restorable: list[M.SnapshotEntry] = []
    seen: set[str] = set()
    for e in snapshot.entries:
        if e.identified and e.key not in seen:
            seen.add(e.key)
            restorable.append(e)
    order = {it.id: i for i, it in enumerate(items)}
    as_items = sorted([e for e in restorable if e.item_id in order], key=lambda e: order[e.item_id])
    rest = [e for e in restorable if e.item_id not in order]
    return as_items + list(reversed(rest))


def unrestorable(snapshot: M.Snapshot) -> list[M.SnapshotEntry]:
    """Entries a restore cannot reopen (unsaved, unidentified, ambiguous), listed rather than dropped."""
    return [e for e in snapshot.entries if not e.identified]
