# Data format (schema 3, and schema 4 below)

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
        {"id": "232133635800", "path": "\\\\fileserver\\p12513\\ISO", "kind": "folder",
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

## Schema 4 (Project Opener 4.0)

`workspace.json` gains four lists and a migration report (the full field reference is
`docs/V4-ARCHITECTURE.md` section 3; the dataclasses are in `core/models.py`):

```
{
  "schema": 4, "app_version": "4.0.0", "saved_at": "...",
  "projects":   [ as schema 3; items gain "profile_id"; launch_sets kept frozen for 3.2 ],
  "activities": [ {id, name, short_name, icon, color, project_ids[], items[ Item + project_id, source_item_id ],
                   owner, created_by, pinned_at, favorite, capture_enabled, resume_on_start, created_at,
                   updated_at, last_opened, open_count, origin} ],
  "profiles":   [ {id, name, app, exe, args, cwd, env{}, description, author, published_id, updated_at} ],
  "watchers":   [ {id, name, kind, target, events[], interval_s, params{}, notify{toast, mentions[], cliq_dm,
                   cliq_channel}, activity_id, project_id, enabled, created_by, created_at} ],
  "migration":  { from_schema, to_schema, at, counts ... }
}
```

| Field | Notes |
|---|---|
| `items[].profile_id` | A `LaunchProfile` id. The launcher starts the item through the profile: `exe` (or the item's own path), `args` with `{ITEM}` (the item's resolved path) and `{VARIABLES}`, `cwd`, and `env` added to the inherited environment. An unknown profile id opens the item plainly and says so in the launch report. |
| `profiles[].args` | Split Windows-style (quoted parts stay together), then expanded, so a path with spaces stays one argument. The built-in presets pass only `"{ITEM}"`; vendor switches are added by people who have checked them. |
| `watchers[].kind` | `folder` (events new/changed/gone; params `pattern` - `;`-separated globs - and `recursive`), `health` (down/up; target a root or "" for all), `hub` (published/task_assigned/task_done/mention; target narrows by id, login or title), `time` (due/stale/reminder; params `stale_days`, `at`, `every_days`, `task_id`, `text`). `interval_s` (minimum 10) applies to folder polling. |

### Bundles (export / import)

`export_bundle` writes `{"schema": 4, "projects", "activities", "profiles"}` (the activities drawing on the
exported projects, and the profiles their items use). `import_bundle` accepts schema 4 (activities and
profiles come along; project ids that change on import are re-pointed in the activities), schema 3 (the
projects' launch sets become activities by the migration rules; importing the same bundle again in merge
mode replaces them rather than duplicating), and the 1.x/2.x forms as before.

### Local runtime files written by the core (data folder)

| File | Format |
|---|---|
| `tasks/<id>.json` | a Task, only while no hub is configured (moved to the hub's `tasks/` when it is reachable) |
| `watch-state/<watcher_id>.json` | `{"files": {relative name: [size, mtime]}, "listed_at"}` - the last folder listing |
| `alerts.jsonl` | one WatchEvent per line `{watcher_id, event, title, detail, path, link, level, ts, key, read}`; `{"read_key", "ts"}` rows mark alerts read; compacted to the newest 500 |
| `delivered.json` | the delivery ledger when no hub is set (`{"schema": 1, "keys": {key: ts}}`); with a hub it is `delivered/<me>.json` there |
| `cliq-outbox.jsonl` | queued Cliq messages `{id, kind: dm or channel, target, text, queued_at, attempts}`; dropped after 50 attempts |

### Settings (4.0 keys used by the core)

`email`, `cliq_user_id`, `cliq_api_base` (default `https://cliq.zoho.in/api/v2`), `cliq_bot` (the bot's
unique name), `cliq_token_enc` (DPAPI blob of the office bot's webhook token), `notify_cliq_default`
(DM me, and show me as Cliq-linked on the hub), `mail_client` (`outlook` or `mailto`).
