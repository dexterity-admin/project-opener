# PRODUCT.md - Project Opener 3

**What it is.** An internal Windows desktop tool for Dexterity Design Services Pvt. Ltd., a piping
design, drafting and QA office. A *project* bundles everything one job needs (isometric PDFs, line
lists, working folders, submission shares, web links, applications with arguments, commands) and
opens all of it with one click. Projects can be published to a Team Hub on a shared folder, cloned,
sent to a colleague's inbox and updated by revision.

**Who uses it.** Piping designers, checkers and QA engineers at their office PCs, several times a
day, usually for a few seconds at a time (open a job, go). Admins mirror updates to the LAN hub.
Everyone is on Windows 10/11 with mapped drives that differ from PC to PC.

**The job on each screen.**

| Screen | Its one question | Most frequent action |
|---|---|---|
| Home | Which job do I open now, and is anything wrong with it? | Open a pinned or recent project |
| Projects | Where is the project I am looking for? | Search, then Open |
| Project | What is in this job and does every path still resolve? | Open project / open one item |
| Team Hub | Who is online, what did the team publish, what is in my inbox? | Clone, Accept, Publish |
| Updates | Am I on the current version, and can I update the office? | Check for updates, Mirror |
| Settings | Where is the hub, how does it look, what runs at start-up? | Toggle, Browse |

**What must stay true.** Paths are the data: the app must never guess or rewrite one silently.
Health states (reachable, not found, server offline, undefined variable) are facts about the evidence.
The LAN hub works without internet. Nothing needs admin rights.

**Tone.** Plain, concrete, the trade's words (job number, client, revision, iso, GAD, line list).
No marketing verbs inside the app.
