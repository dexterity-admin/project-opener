"""Rotating file logging plus an in-memory ring buffer the UI can show."""
from __future__ import annotations

import collections
import logging
import logging.handlers
from pathlib import Path

from project_opener import constants as C

RING: collections.deque[str] = collections.deque(maxlen=400)


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            RING.append(self.format(record))
        except Exception:  # pragma: no cover
            pass


def setup_logging(level: int = logging.INFO) -> Path:
    log_dir = C.data_dir() / C.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "project-opener.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        fh = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
        rh = _RingHandler()
        rh.setFormatter(fmt)
        root.addHandler(rh)
    return path
