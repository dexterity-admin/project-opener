# Data format (schema 3)

`workspace.json` is a plain UTF-8 JSON document. It is written atomically and a timestamped backup is
kept before every write. All timestamps are ISO-8601 in UTC.

```json
{
  "schema": 3,
  "app_version": "3.0.0",
  "saved_at": "2026-10-31T17:20:00+00:00",
  "projects": [
    {
      "id": "f1be49723cd8",
      "name": "P12513 As-built isometrics",
      "description": "RLM red-line cross-check lot 7",
      "notes": "",
      "color": "#2F5BFF",
      "icon": "fa5s.drafting-compass",
      "tags": ["as-built", "FST"],
      "client": "FST",
      "job_number": "P12513",
      "items": [
        {"id": "232133635800", "path": "\\\\192.168.0.12\\p12513\\ISO", "kind": "folder",
         "label": "Submission share", "args": "", "enabled": true, "group": "Folders",
         "added_at": "2026-10-31T17:00:00+00:00"},
        {"id": "909ded27bfc0", "path": "{SERVER_ROOT}\\P12513\\Rulings.docx", "kind": "file",
         "label": "", "args": "", "enabled": true, "group": "References", "added_at": "..."}
      ],
      "launch_sets": [
        {"id": "a1", "name": "Checking", "item_ids": ["232133635800"], "icon": "fa5s.rocket"}
      ],
      "pinned_at": "2026-10-31T17:05:00+00:00",
      "favorite": true,
      "auto_launch": false,
      "created_at": "...", "updated_at": "...", "last_opened": "...", "open_count": 14,
      "origin": {"source": "team", "author": "yokesh", "published_id": "5c0d…", "published_at": "...", "revision": 2}
    }
  ]
}
```

## Fields

| Field | Notes |
|---|---|
| `kind` | `file`, `folder`, `url`, `app`, `command`. Unknown values are re-guessed from the path. |
| `path` | Stored verbatim. May contain `{VARIABLES}`, `%ENV%` variables, drive letters or UNC paths. `cmd:` / `ps:` prefixes mark commands. |
| `args` | Only used for `app` (and `.bat/.cmd`). Variables are resolved inside arguments too. |
| `enabled` | Whether "Open project" includes the item. Launch sets ignore this flag. |
| `group` | Free text heading in the detail page; also the v2 "activity" name after migration. |
| `pinned_at` | `null` when unpinned; pinned projects sort by this timestamp. |
| `origin.source` | `local` (created here), `team` (cloned from the hub), `inbox` (received), `import`. |
| `origin.revision` | Hub revision this clone was taken from; a higher published revision shows an *Update from hub* banner. |

## Tolerance rules

`Project.from_dict` never raises on bad input: missing fields get defaults, invalid colours fall back
to the default blue, non-dict items are skipped, numeric strings are coerced. This matters because hub
files are written by other machines running other versions.

## Legacy formats

| Version | Location | How it is read |
|---|---|---|
| 1.x | `%APPDATA%\ProjectOpener\projects.json` + `auto_launch.json` (dict of name → `{files, notes, color, last_opened, pinned}`) | migrated automatically on first run; also *Settings → Data → Import from 1.x* |
| 1.x export | `{"projects": {...}, "auto_launch": {...}}` | *Settings → Data → Import* (merge or replace) |
| 2.x | `<hub>/<user>.json` with `projects → activities → items {type, path, args}` | *Settings → Data → Import* detects it; activities become launch sets and item groups |
| 3.x export | `{"schema": 3, "projects": [...]}` | *Import* (merge by id/name, or replace) |

## Settings (`settings.json`)

Typed by `core/settings.py::Settings`. Notable keys: `theme`, `accent`, `density`, `hub_path`,
`variables` (`{"{SERVER_ROOT}": "\\\\server\\share"}`), `update_channel`, `github_token_enc`
(DPAPI blob, `dpapi:` prefix), `window_geometry` (base64 of `QMainWindow.saveGeometry`).

## History (`history.jsonl`)

One JSON object per launch: `{"ts", "project_id", "project", "set", "count", "ok", "missing"}`.
Used for the dashboard's recent activity and stats; safe to delete.
