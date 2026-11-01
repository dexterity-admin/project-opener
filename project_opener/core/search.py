"""Fuzzy search used by the command palette and the project grid.

Scoring is deliberately simple and deterministic: exact prefix > word prefix >
subsequence, with a small bonus for pinned / recently opened projects so the
thing you want is usually the first hit.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from project_opener.core import models as M


@dataclass
class Hit:
    kind: str            # project | item | set | action
    title: str
    subtitle: str
    score: float
    project: M.Project | None = None
    item: M.Item | None = None
    launch_set: M.LaunchSet | None = None
    action_id: str = ""
    icon: str = "fa5s.folder"


def subsequence_score(query: str, text: str) -> float:
    """0 when not a subsequence, otherwise higher is better (max ~1)."""
    q = query.lower()
    t = text.lower()
    if not q:
        return 0.5
    if t.startswith(q):
        return 1.0
    idx = t.find(q)
    if idx >= 0:
        # whole substring; reward word boundaries
        boundary = idx == 0 or not t[idx - 1].isalnum()
        return 0.85 if boundary else 0.7
    # subsequence with gaps
    pos = 0
    gaps = 0
    for ch in q:
        nxt = t.find(ch, pos)
        if nxt < 0:
            return 0.0
        gaps += nxt - pos
        pos = nxt + 1
    return max(0.1, 0.6 - min(gaps, 40) * 0.01)


def search_projects(query: str, projects: Iterable[M.Project], limit: int = 20) -> list[Hit]:
    hits: list[Hit] = []
    q = query.strip()
    for p in projects:
        best = subsequence_score(q, p.name)
        if q and best < 0.4:
            for field in (p.client, p.job_number, p.description, " ".join(p.tags)):
                if field:
                    best = max(best, subsequence_score(q, field) * 0.8)
        if q and best <= 0 and q.lower() in p.search_blob():
            best = 0.3
        if best > 0:
            bonus = (0.15 if p.pinned else 0) + (0.05 if p.last_opened else 0)
            n = len(p.items)
            hits.append(Hit("project", p.title, p.description or f"{n} item{'s' if n != 1 else ''}", best + bonus,
                            project=p, icon=p.icon))
    hits.sort(key=lambda h: (-h.score, h.title.lower()))
    return hits[:limit]


def search_everything(query: str, projects: Iterable[M.Project], actions: list[tuple[str, str, str]] | None = None,
                      limit: int = 30) -> list[Hit]:
    """Projects, launch sets, items and palette actions, ranked together."""
    projects = list(projects)
    hits = search_projects(query, projects, limit=limit)
    q = query.strip()
    if q:
        for p in projects:
            for s in p.launch_sets:
                sc = subsequence_score(q, s.name)
                if sc > 0.3:
                    hits.append(Hit("set", s.name, f"Launch set in {p.title}", sc * 0.9, project=p, launch_set=s,
                                    icon=s.icon))
            for it in p.items:
                sc = max(subsequence_score(q, it.display_name), subsequence_score(q, it.path) * 0.7)
                if sc > 0.3:
                    hits.append(Hit("item", it.display_name, f"{p.title}  ·  {it.path}", sc * 0.8, project=p, item=it,
                                    icon=item_icon(it)))
    action_hits = []
    for action_id, title, icon in actions or []:
        sc = subsequence_score(q, title) if q else 0.2
        if sc > 0.3 or not q:
            action_hits.append(Hit("action", title, "Action", sc * 0.95, action_id=action_id, icon=icon))
    if not q:
        # Empty query: projects first, then every action, so the actions never
        # drop off the end of a long project list.
        hits.sort(key=lambda h: (-h.score, h.title.lower()))
        return hits[:max(0, limit - len(action_hits))] + action_hits
    hits.extend(action_hits)
    hits.sort(key=lambda h: (-h.score, h.title.lower()))
    return hits[:limit]


def item_icon(item: M.Item) -> str:
    low = item.path.lower()
    if item.kind == "url":
        if "teams" in low:
            return "fa5b.microsoft"
        return "fa5s.link"
    if item.kind == "folder":
        return "fa5s.folder-open"
    if item.kind == "app":
        return "fa5s.rocket"
    if item.kind == "command":
        return "fa5s.terminal"
    if low.endswith(".pdf"):
        return "fa5s.file-pdf"
    if low.endswith((".xls", ".xlsx", ".xlsm", ".csv")):
        return "fa5s.file-excel"
    if low.endswith((".doc", ".docx")):
        return "fa5s.file-word"
    if low.endswith((".dwg", ".dgn", ".dxf", ".i01", ".rvt", ".nwd", ".nwf", ".nwc")):
        return "fa5s.drafting-compass"
    if low.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".svg")):
        return "fa5s.file-image"
    if low.endswith((".zip", ".7z", ".rar")):
        return "fa5s.file-archive"
    if low.endswith((".py", ".ps1", ".bat", ".cmd", ".js", ".ts", ".json")):
        return "fa5s.file-code"
    if low.endswith((".txt", ".md", ".log")):
        return "fa5s.file-alt"
    return "fa5s.file"
