"""Extract useful compiler diagnostics from Gradle output."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .validation import SOURCE_ROOT

# Kotlin 2.x: "e: file:///abs/path/app/src/main/java/com/genesis/app/Foo.kt:12:5 Unresolved reference 'x'."
# Also handles Windows paths: "e: C:\path\..." or "e: file://C:\..."
KOTLIN_DIAG_RE = re.compile(
    r"^(?P<sev>[ew]): (?:file://)?(?P<path>(?:/(?=[a-zA-Z]:))?(?:[a-zA-Z]:[\\/]|[/\\])[^:\n]+\.kts?):(?P<line>\d+):(?P<col>\d+) (?P<msg>.+)$",
    re.MULTILINE,
)


@dataclass
class Diagnostic:
    severity: str  # "error" | "warning"
    rel_path: str | None  # relative to SOURCE_ROOT when inside generated sources
    line: int
    column: int
    message: str

    def render(self) -> str:
        where = f"{self.rel_path}:{self.line}:{self.column}" if self.rel_path else f"line {self.line}"
        return f"{self.severity}: {where} {self.message}"


def _rel(path: str) -> str | None:
    norm = path.replace("\\", "/")
    marker = "/" + SOURCE_ROOT + "/"
    i = norm.find(marker)
    return norm[i + len(marker):] if i >= 0 else None


def parse_diagnostics(output: str, *, limit: int = 40) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    seen: set[tuple] = set()
    for m in KOTLIN_DIAG_RE.finditer(output):
        sev = "error" if m.group("sev") == "e" else "warning"
        msg = m.group("msg").strip()
        # Multi-line messages (e.g. overload candidates) continue on indented lines.
        tail = re.match(r"((?:\n[ \t]+\S[^\n]*){1,8})", output[m.end():])
        if tail:
            msg += " " + " | ".join(line.strip() for line in tail.group(1).strip("\n").splitlines())
        d = Diagnostic(sev, _rel(m.group("path")), int(m.group("line")), int(m.group("col")), msg[:700])
        key = (d.severity, d.rel_path, d.line, d.column, d.message)
        if key not in seen:
            seen.add(key)
            diags.append(d)
    diags.sort(key=lambda d: d.severity != "error")
    return diags[:limit]


def failure_summary(output: str, *, max_lines: int = 30) -> str:
    """Gradle's own 'What went wrong' section, for failures that are not Kotlin diagnostics."""
    m = re.search(r"\* What went wrong:\n([\s\S]*?)(?:\n\* Try:|\Z)", output)
    text = m.group(1) if m else output[-4000:]
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return "\n".join(lines[:max_lines])


def errors_only(diags: list[Diagnostic]) -> list[Diagnostic]:
    return [d for d in diags if d.severity == "error"]
