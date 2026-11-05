"""Capture and restore (brief sections 3.1 and 3.8; spikes/capture/REPORT.md).  Owner: builder 2 (CAPTURE).

Layering: imports ``core`` only (never ``quick``, ``desktop`` or ``ui``).  Every
COM call happens on the one capture thread owned by ``engine.CaptureEngine``
(its own ``CoInitializeEx``).  Deterministic plumbing only: nothing here
decides what a window "probably" is; unknown stays unidentified.

    win32.py      window enumeration, placement, monitors, processes, foreground, cloaking
    sources/      one module per identification source (explorer, office, browser, titles)
    identify.py   Identifier: sources in order + the identity cache
    diff.py       pure: snapshot vs items, snapshot vs snapshot, "new since checkpoint"
    engine.py     CaptureEngine: the thread, the pass cadence, the request queue
    restore.py    Restorer: reopen in order (Office via COM), settle, match by identity, place
    windows.py    "add this window" / "start from what's open" helpers over Identifier
"""
