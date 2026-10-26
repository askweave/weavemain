"""Access code for remote clients (the Genesis phone app). The local dashboard on 127.0.0.1 needs none."""

from __future__ import annotations

import hmac
import os
import secrets
import socket
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

# Crockford-style alphabet: no 0/O, 1/I/L, U confusion. 16 chars x 5 bits = 80 bits.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"


def normalize_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def format_code(raw: str) -> str:
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def generate_code() -> str:
    return format_code("".join(secrets.choice(ALPHABET) for _ in range(16)))


def load_or_create_code(data_dir: Path) -> str:
    """GENESIS_ACCESS_CODE wins; otherwise a random code persisted to data/access_code (mode 600)."""
    env = os.environ.get("GENESIS_ACCESS_CODE", "").strip()
    if env:
        if len(normalize_code(env)) < 12:
            raise ValueError("GENESIS_ACCESS_CODE must have at least 12 letters/digits")
        return env
    path = data_dir / "access_code"
    if path.is_file():
        code = path.read_text().strip()
        if len(normalize_code(code)) >= 12:
            return code
    data_dir.mkdir(parents=True, exist_ok=True)
    code = generate_code()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(code + "\n")
    return code


def check_code(presented: str, expected: str) -> bool:
    a, b = normalize_code(presented), normalize_code(expected)
    return bool(a) and hmac.compare_digest(a.encode(), b.encode())


class FailureLimiter:
    """Block a client IP after repeated wrong access codes."""

    def __init__(self, max_failures: int = 10, window_s: float = 600):
        self.max, self.window = max_failures, window_s
        self.failures: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def _prune(self, ip: str, now: float) -> deque[float]:
        q = self.failures[ip]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, ip: str) -> bool:
        with self.lock:
            return len(self._prune(ip, time.monotonic())) >= self.max

    def record(self, ip: str) -> None:
        with self.lock:
            self._prune(ip, time.monotonic()).append(time.monotonic())


def lan_addresses() -> list[str]:
    """Best-effort private IPv4 addresses of this machine (for showing the phone which URL to use)."""
    addrs: set[str] = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent for UDP connect
        addrs.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    return sorted(a for a in addrs if not a.startswith("127."))
