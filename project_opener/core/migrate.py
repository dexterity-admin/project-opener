"""Workspace migration from schema 3 (Project Opener 3.x) to schema 4.

Pure functions over dicts and dataclasses: no files, no Qt.  ``WorkspaceStore``
calls ``migrate_workspace`` when it loads a workspace whose ``schema`` is
below 4, after writing a ``pre-v4-workspace-*.json`` copy that the backup
rotation never deletes.  The rules are in docs/V4-ARCHITECTURE.md section 4:

1. Projects stay exactly as they were (every field; items gain ``profile_id``).
2. Every launch set of every project becomes one ``Activity``: same id, same
   name, same icon, the project's colour, ``project_ids = [project.id]``, and
   the set's items as ``ActivityItem`` copies in the set's order, linked back
   through ``project_id``/``source_item_id``.  Launch sets ignored ``enabled``,
   so the copies are all enabled.  Ids that pointed at no item are counted in
   the report (they opened nothing in 3.x either).
3. A *pinned* project with no launch sets also becomes one activity (named
   after the project, its enabled items), so Home's stage is not empty for
   people who never made a set.  Set ``pinned_projects_as_activities=False``
   to skip.
4. Launch sets stay on the projects, frozen, so a 3.2 PC reading the same
   workspace or a project published from 4.0 still sees them.
5. Nothing is dropped; the report records counts for support.
"""
from __future__ import annotations

from typing import Any

from project_opener.core import models as M

TARGET_SCHEMA = 4


def activity_from_launch_set(project: M.Project, launch_set: M.LaunchSet) -> tuple[M.Activity, int]:
    """One 3.x launch set as a v4 activity.  Returns (activity, dangling item ids)."""
    by_id = {i.id: i for i in project.items}
    items: list[M.ActivityItem] = []
    dangling = 0
    seen: set[str] = set()
    for iid in launch_set.item_ids:
        item = by_id.get(iid)
        if item is None:
            dangling += 1
            continue
        if iid in seen:          # a set listing the same item twice opened it twice; keep one
            continue
        seen.add(iid)
        copy = M.ActivityItem.from_item(item, project_id=project.id, source_item_id=item.id)
        copy.enabled = True
        items.append(copy)
    act = M.Activity(
        name=launch_set.name.strip() or "Activity",
        id=launch_set.id or M.new_id(),
        icon=launch_set.icon or "",
        color=project.color,
        project_ids=[project.id],
        items=items,
        owner=M.current_user(),
        created_by=project.origin.author or M.current_user(),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
    return act, dangling


def activity_from_project(project: M.Project) -> M.Activity:
    """A pinned project without launch sets as one activity of its enabled items."""
    items = [M.ActivityItem.from_item(i, project_id=project.id, source_item_id=i.id) for i in project.enabled_items]
    return M.Activity(name=project.name, icon=project.icon, color=project.color, project_ids=[project.id],
                      items=items, pinned_at=project.pinned_at, created_by=project.origin.author or M.current_user(),
                      created_at=project.created_at, updated_at=project.updated_at,
                      last_opened=project.last_opened)


def migrate_projects(projects: list[M.Project], pinned_projects_as_activities: bool = True,
                     existing_ids: set[str] | None = None) -> tuple[list[M.Activity], dict[str, Any]]:
    """The activities that 3.x projects imply, plus a report.  The projects are not modified."""
    taken = set(existing_ids or ())
    activities: list[M.Activity] = []
    report: dict[str, Any] = {"launch_sets": 0, "activities_from_sets": 0, "activities_from_pinned": 0,
                              "items_copied": 0, "dangling_item_ids": 0, "projects": len(projects)}
    for proj in projects:
        for ls in proj.launch_sets:
            report["launch_sets"] += 1
            act, dangling = activity_from_launch_set(proj, ls)
            if act.id in taken:
                act.id = M.new_id()
            taken.add(act.id)
            activities.append(act)
            report["activities_from_sets"] += 1
            report["items_copied"] += len(act.items)
            report["dangling_item_ids"] += dangling
        if pinned_projects_as_activities and proj.pinned and not proj.launch_sets and proj.enabled_items:
            act = activity_from_project(proj)
            taken.add(act.id)
            activities.append(act)
            report["activities_from_pinned"] += 1
            report["items_copied"] += len(act.items)
    return activities, report


def migrate_workspace(data: dict[str, Any], pinned_projects_as_activities: bool = True) -> M.Workspace:
    """A raw ``workspace.json`` dict of any schema up to 4 as a schema-4 ``Workspace``.

    Schema 4 input is returned as parsed (idempotent).  Schema 3 (or a dict
    without ``schema`` but with a ``projects`` list) is migrated.
    """
    ws = M.Workspace.from_dict(data if isinstance(data, dict) else {})
    source_schema = ws.schema
    if source_schema >= TARGET_SCHEMA:
        ws.schema = TARGET_SCHEMA
        return ws
    activities, report = migrate_projects(ws.projects, pinned_projects_as_activities,
                                          existing_ids={a.id for a in ws.activities})
    ws.activities = list(ws.activities) + activities
    report.update({"from_schema": source_schema, "to_schema": TARGET_SCHEMA, "at": M.now_iso(),
                   "from_app_version": str((data or {}).get("app_version", "")) if isinstance(data, dict) else ""})
    ws.migration = report
    ws.schema = TARGET_SCHEMA
    return ws
