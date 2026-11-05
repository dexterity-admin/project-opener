"""Explorer entries, per user, no admin.  Owner: builder 3 (DESKTOP).

* Verb "Add to running activity" on files and folders::

    HKCU\\Software\\Classes\\*\\shell\\<EXPLORER_VERB>                 (MUIVerb, Icon)
    HKCU\\Software\\Classes\\Directory\\shell\\<EXPLORER_VERB>
        \\command  = "<exe>" --add "%1"

  A "%1" verb on a multi-selection starts one process per file, so the
  running instance batches ``add`` commands that arrive within 500 ms into
  one chooser / one toast.  Send to is the many-files route.
* Send to: ``%APPDATA%\\Microsoft\\Windows\\SendTo\\<SENDTO_NAME>`` pointing at
  ``"<exe>" --sendto`` (Windows appends every selected path).

The installer (installer/ProjectOpener.iss) writes the same keys; the app can
add or remove them from Settings > Snapshot.  Source runs (not frozen) use
``pythonw -m project_opener --v4``.
"""
from __future__ import annotations


def command_line() -> str:
    """The exe (frozen) or ``pythonw -m project_opener --v4`` (source) that the entries call."""
    raise NotImplementedError("command_line")


def install_explorer_verb() -> bool:
    raise NotImplementedError("install_explorer_verb")


def remove_explorer_verb() -> bool:
    raise NotImplementedError("remove_explorer_verb")


def explorer_verb_installed() -> bool:
    raise NotImplementedError("explorer_verb_installed")


def install_sendto() -> bool:
    raise NotImplementedError("install_sendto")


def remove_sendto() -> bool:
    raise NotImplementedError("remove_sendto")


def sendto_installed() -> bool:
    raise NotImplementedError("sendto_installed")
