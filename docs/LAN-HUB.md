# Team Hub (LAN collaboration)

The Team Hub turns any shared folder on the office network into a collaboration space. There is no
server process, no database and nothing to install on the file server: every Project Opener instance
reads and writes small JSON files under one folder.

## Setting it up (once per office)

1. Create a folder every colleague can read **and write**, for example
   `\\nas01\Project\_ProjectOpenerHub`.
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

## 4.0 additions (hub schema 2)

A 4.x PC that connects sets `"schema": 2` in `hub.json` and creates the new folders. 3.2 PCs keep
working on the same hub: they ignore the number and skip every file they do not understand
(published and inbox files without a `"project"` key are invisible to them, not errors).

```
_ProjectOpenerHub/
├── users/<user>.json        + "email", "cliq_id", "cliq_linked", "current_activity"
├── groups.json              {"schema": 1, "groups": [{name, members[], color, created_by, updated_by, updated_at}]}
├── published/<id>.json      + "type": "project" | "activity", "for": ["yokesh", "checkers"]
│                            activities: {"schema": 2, "type": "activity", "published_id", "author", "author_name",
│                                         "published_at", "revision", "description", "for", "activity": {...},
│                                         "projects": [{id, title, job_number}]}
├── inbox/<user>/<id>.json   + "kind": project | activity | mention | task
│                            mention: {"schema": 2, "id", "kind": "mention", "from", "from_name", "to", "sent_at",
│                                      "text", "link", "title" (optional)}
│                            task:    the same with "kind": "task" and "task_id"
├── tasks/<id>.json          one task per file (title, owner, due, created/updated by/at, done_at/by, link, note)
├── watch/<user>.json        {"schema": 1, "user", "host", "ts", "roots": [{root, status, since, jobs[], items}]}
├── delivered/<user>.json    {"schema": 1, "keys": {event_key: ts}} - newest 2,000
├── profiles/<id>.json       shared launch profiles
├── announcements.json       items gain "mentions" and "author_name"
└── pulse/<user>.jsonl       rows gain "kind" (launched|published|sent|task|mention|watch), "mentions",
                             "task_id", "activity"; 3.2 still reads "event" and "detail"
```

### Concurrency (4.0 files)

| File | Writers | Strategy |
|---|---|---|
| `groups.json` | anyone | re-read, apply one change, atomic replace; last writer wins; `updated_by` records who |
| `tasks/<id>.json` | anyone (everyone equal) | one file per task, atomic replace, last writer wins; `updated_by`/`updated_at` record who |
| `published/<id>.json` (activity) | anyone may republish | atomic replace, `revision` increments, `author` is the last publisher; a republish without project information keeps the earlier `projects` list |
| `watch/<me>.json`, `delivered/<me>.json` | only me (any of my PCs) | atomic replace; the ledger is re-read before each write |
| `profiles/<id>.json` | anyone | atomic replace, last writer wins |

Names that become file or folder names (logins, ids) must match `[A-Za-z0-9][A-Za-z0-9 ._$-]*` and never
contain `..`; anything else is refused rather than written.

### People: mentions, groups, "for"

- `@name` in a publish description, announcement, task title or note is a mention (`core.mentions`):
  it must start the text or follow a space or bracket, so `name@company.com` is not one.
- `for` lists and mentions hold logins and group names without `@`, lower case. Readers expand groups one
  level and drop names nobody on the hub has used (`users/*.json`), so a typo reaches nobody. Nobody is sent
  their own note.
- Publishing *for* people writes the published file **and** an inbox entry per person reached (kind
  `project`, which a 3.2 PC also shows, or `activity`), tags the pulse row, and DMs the people who linked Cliq.
- Groups: anyone may create, edit or delete one. *Make a group from this job* collects the people the hub
  shows holding it: the publisher, the published file's `for`, and everyone whose pulse mentions the job
  number or title.

### Activities on the hub

Published and sent activities carry their items with portable paths, exactly as projects (drive letter to
UNC through the publisher's drive map; `{VARIABLES}` and URLs unchanged). On *Accept* or *Clone* the
activity gets fresh ids; a link to a project survives only when the receiver has that project id or exactly
one project with the recorded job number, and an item link only when that project has the item (same id, or
exactly one item with the same path). Anything else becomes a plain item - never a guessed link.

### Tasks

`tasks/<id>.json` per task. Assigning someone else writes a `task` inbox entry and DMs them; marking done
pulses "<name> finished <title>" and tells the creator. Without a hub, tasks live in the data folder's
`tasks/` in the same format and move to the hub the first time it is reachable.

### Office-wide path health

Every PC writes what it sees of its roots (drive letters folded into their server, `{VARIABLES}`) to
`watch/<me>.json`; `since` is when this PC first saw the current status. Every PC merges the fresh files
(younger than 3 minutes): worst status, the PCs that saw it, the PCs that still reach it, the earliest
`since`, and the union of jobs - "\\nas01 offline since 09:40, seen by 3 PCs, 14 jobs affected". A root one PC
sees down and others reach is shown that way, not hidden.

### Alerts exactly once

Every alert has a stable key (watcher id + event + what it is about, never the time of the check).
`delivered/<me>.json` records the keys delivered (newest 2,000); a key already there is not toasted,
pulsed, written to inboxes or sent to Cliq again - also not by my other PC. Inbox entries are toasted
once under the key `inbox:<id>`; entries older than three days found on first contact are recorded
silently.

### Zoho Cliq

One office bot under a shared service account. Its **webhook token** (Cliq: Bots & Tools > Webhook Tokens;
it does not expire, at most 5 per user) is entered once in Settings and stored with DPAPI. Endpoints used,
from Zoho's documentation (verified 5 November 2026):

| Use | Request |
|---|---|
| DM people | `POST {base}/bots/{bot}/message?zapikey=TOKEN` with `{"text", "userids": "id1,id2"}` |
| Post to a channel | `POST {base}/channelsbyname/{channel}/message?zapikey=TOKEN&bot_unique_name={bot}` with `{"text"}` |
| Find my user id | `GET {base}/users/{email}` - documented for OAuth (`ZohoCliq.Users.READ`); with the webhook token it may be refused, in which case the user pastes the id in Settings |

`base` defaults to `https://cliq.zoho.in/api/v2` (other data centres: cliq.zoho.com, .eu, .com.au, .jp,
.com.cn, .sa, .uk, cliq.zohocloud.ca). A user receives bot DMs only after subscribing to the bot. Network
failures, 429 and 5xx are queued in the data folder's `cliq-outbox.jsonl` and retried every 5 minutes; other
refusals are logged and dropped. Sources: <https://www.zoho.com/cliq/help/platform/webhook-tokens.html>,
<https://www.zoho.com/cliq/help/restapi/v2/>.
