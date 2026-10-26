"""Structured SMS events: one key=value log line each, plus in-process counters for /api/sms/status.
Callers pass masked phone numbers and never message bodies, tokens or source code."""

from __future__ import annotations

import logging
import threading
from collections import Counter

log = logging.getLogger("genesis.sms")
_counts: Counter[str] = Counter()
_lock = threading.Lock()


def event(name: str, level: int = logging.INFO, **fields: object) -> None:
    with _lock:
        _counts[name] += 1
    parts = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    log.log(level, "event=%s %s", name, parts)


def counters() -> dict[str, int]:
    with _lock:
        return dict(_counts)
