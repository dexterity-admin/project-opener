# Team Hub (LAN collaboration)

The Team Hub turns any shared folder on the office network into a collaboration space. There is no
server process, no database and nothing to install on the file server: every Project Opener instance
reads and writes small JSON files under one folder.

## Setting it up (once per office)

1. Create a folder every colleague can read **and write**, for example
   `\\192.168.0.200\Project\_ProjectOpenerHub`.
2. In Project Opener: **Settings → Team Hub → Browse… → Connect**. The app creates the layout below.
3. Everyone else enters the same path. That's it.

Tip: *Settings → Path variables → Add my mapped drives* creates `{Z_DRIVE}`-style variables so
published projects open on PCs whose drive letters differ.

## Folder layout

```
_ProjectOpenerHub/
├── hub.json                 identity + schema version
├── users/<user>.json        heartbeat every 60 s: display name, role, machine, app version,
│                            current project (if "Share my activity" is on)
├── published/<id>.json      team projects (author, revision counter, portable paths)
├── inbox/<user>/<id>.json   projects sent directly to one colleague (accept or dismiss)
├── announcements.json       banners shown on everyone's Home page (info / warning / critical)
├── pulse/<user>.jsonl       opt-in activity feed (launched, published, sent)
└── updates/                 LAN update mirror: latest.json + ProjectOpener-Setup-X.Y.Z.exe
```

## Concurrency model

| File | Writers | Strategy |
|---|---|---|
| `users/<me>.json`, `pulse/<me>.jsonl` | only me | no conflicts possible |
| `inbox/<you>/<id>.json` | sender creates, recipient deletes | unique id per message |
| `published/<id>.json` | the author (anyone may re-publish their own) | atomic replace, `revision` increments; clones compare revisions |
| `announcements.json` | anyone | small file, atomic replace, last writer wins (max 50 kept) |

All writes are temp-file + `os.replace`, so readers never see a half-written file. Readers tolerate
corrupt or foreign files (they are skipped and logged), so one bad file never breaks the hub.

## Presence

- **Hub heartbeat** (always on when a hub is set): `users/<me>.json` is rewritten every 60 s and
  marked offline on exit. A peer is "online" if the heartbeat is younger than 3 minutes.
- **UDP beacon** (optional, *Settings → Team Hub → Fast LAN presence*): a JSON datagram is broadcast
  to `255.255.255.255:48620` every 15 s, so online status updates within seconds on the same subnet.
  Inbound datagrams may be blocked by Windows Firewall for a per-user install; the hub heartbeat
  remains the source of truth, the beacon only makes it faster.

## Sharing projects

- **Publish** (project menu → *Publish to Team Hub*): the project is written to `published/` with drive
  letters converted to UNC paths. Re-publishing bumps the revision; colleagues who cloned it see an
  *Update from hub* banner on the project page.
- **Clone**: Team Hub → Published → *Clone* copies it into your workspace with fresh ids and remembers
  its `published_id` / `revision`.
- **Send to colleague**: project menu → *Send to colleague…* drops it into their inbox with a note.
  They *Accept* (added to their workspace) or *Dismiss*.
- **Announcements**: Team Hub → Announcements → *Post*. Authors can remove their own.

## Privacy

*Share my activity* controls both the "current project" in the heartbeat and the pulse feed.
Turning it off keeps presence (online/offline) but publishes nothing else.
