"""Validation of model-generated files before anything touches a workspace.

Generated code is only ever compiled on this machine, never executed here; the checks below keep
the model inside the approved source tree and away from build configuration, and keep obviously
dangerous APIs out of the APK (the template grants no Android permissions either).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from .schemas import AppManifest, GeneratedFile, RepairPatch

SOURCE_ROOT = "app/src/main/java/com/genesis/app"
BASE_PACKAGE = "com.genesis.app"

MAX_FILES = 20
MAX_FILE_BYTES = 60_000
MAX_TOTAL_BYTES = 250_000
ALLOWED_SUFFIXES = {".kt"}

# Server-controlled files inside the source root that the model may not replace.
PROTECTED_FILES = {"MainActivity.kt"}
PROTECTED_DIRS = ("ui/theme/", "ui/kit/")
KIT_IMPORT_RE = re.compile(r"^\s*import\s+com\.genesis\.app\.ui\.kit\.", re.MULTILINE)

SEGMENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
FILE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}\.kt$")

# APIs that have no business in Phase 1 offline apps. Matched against code with comments/strings stripped.
FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("process execution", re.compile(r"\bRuntime\s*\.\s*getRuntime\b|\bProcessBuilder\b")),
    ("dynamic code loading", re.compile(r"\b(DexClassLoader|PathClassLoader|InMemoryDexClassLoader|URLClassLoader)\b|\bSystem\s*\.\s*load(Library)?\b|\bClass\s*\.\s*forName\b")),
    ("networking", re.compile(r"\bjava\.net\b|\bHttpURLConnection\b|\bokhttp3?\b|\bretrofit2?\b|\bSocket\b|\bandroid\.net\.http\b")),
    ("reflection", re.compile(r"\bkotlin\.reflect\.full\b|\bjava\.lang\.reflect\b|\.getDeclaredMethod\b|\.getDeclaredField\b")),
    ("native code", re.compile(r"\bexternal\s+fun\b|@JvmStatic\s+external\b")),
    ("shell/su", re.compile(r"\"/system/bin|\"su\"")),
    ("webview", re.compile(r"\bWebView\b")),
    ("unapproved libraries", re.compile(r"^\s*import\s+(?!androidx\.|android\.|kotlin\.|kotlinx\.coroutines\.|java\.util\.|java\.time\.|java\.text\.|java\.io\.Serializable|org\.json\.|com\.genesis\.app\b)", re.MULTILINE)),
]


class ValidationError(ValueError):
    """Raised when generated output fails a safety or structure check."""


@dataclass
class ValidatedFile:
    rel_path: str  # relative to SOURCE_ROOT, POSIX style
    content: str

    @property
    def workspace_path(self) -> str:
        return f"{SOURCE_ROOT}/{self.rel_path}"


def normalize_rel_path(raw: str) -> str:
    """Return a safe relative path inside SOURCE_ROOT, or raise."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValidationError("empty file path")
    p = raw.strip().replace("\\", "/")
    # Accept a model that repeated the full source root prefix.
    for prefix in (SOURCE_ROOT + "/", "src/main/java/com/genesis/app/", "com/genesis/app/"):
        if p.startswith(prefix):
            p = p[len(prefix):]
            break
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        raise ValidationError(f"absolute paths are not allowed: {raw!r}")
    if "\x00" in p or any(ord(c) < 32 for c in p):
        raise ValidationError(f"control characters in path: {raw!r}")
    parts = tuple(p.split("/"))
    if not parts or any(part in ("..", ".", "") for part in parts):
        raise ValidationError(f"path traversal is not allowed: {raw!r}")
    if len(parts) > 4:
        raise ValidationError(f"path is nested too deeply: {raw!r}")
    *dirs, name = parts
    if PurePosixPath(name).suffix not in ALLOWED_SUFFIXES or not FILE_RE.fullmatch(name):
        raise ValidationError(f"only Kotlin source files (*.kt) are allowed: {raw!r}")
    for d in dirs:
        if not SEGMENT_RE.fullmatch(d) or d != d.lower():
            raise ValidationError(f"invalid package directory {d!r} in {raw!r}")
    rel = "/".join(parts)
    if rel in PROTECTED_FILES or rel.lower().startswith(PROTECTED_DIRS):
        raise ValidationError(f"{rel} is a protected template file")
    return rel


def strip_comments_and_strings(code: str) -> str:
    """Rough Kotlin lexer pass so forbidden-API checks ignore comments and string literals."""
    code = re.sub(r'"""[\s\S]*?"""', '""', code)
    code = re.sub(r"/\*[\s\S]*?\*/", " ", code)
    code = re.sub(r"//[^\n]*", "", code)
    code = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', code)
    return code


def expected_package(rel_path: str) -> str:
    dirs = list(PurePosixPath(rel_path).parts[:-1])
    return ".".join([BASE_PACKAGE, *dirs])


def validate_file(f: GeneratedFile) -> ValidatedFile:
    rel = normalize_rel_path(f.path)
    content = f.content.replace("\r\n", "\n")
    size = len(content.encode("utf-8"))
    if size == 0 or not content.strip():
        raise ValidationError(f"{rel} is empty")
    if size > MAX_FILE_BYTES:
        raise ValidationError(f"{rel} is {size} bytes (limit {MAX_FILE_BYTES})")
    pkg = re.search(r"^\s*package\s+([\w.]+)", content, re.MULTILINE)
    want = expected_package(rel)
    if not pkg or pkg.group(1) != want:
        raise ValidationError(f"{rel} must declare `package {want}`")
    stripped = strip_comments_and_strings(content)
    for label, pattern in FORBIDDEN_PATTERNS:
        m = pattern.search(stripped)
        if m:
            snippet = m.group(0).strip()[:80]
            raise ValidationError(f"{rel} uses a disallowed API ({label}): {snippet!r}")
    return ValidatedFile(rel, content if content.endswith("\n") else content + "\n")


def _validate_files(files: list[GeneratedFile]) -> list[ValidatedFile]:
    if len(files) > MAX_FILES:
        raise ValidationError(f"too many files ({len(files)}, limit {MAX_FILES})")
    out: list[ValidatedFile] = []
    seen: set[str] = set()
    for f in files:
        vf = validate_file(f)
        if vf.rel_path.lower() in seen:
            raise ValidationError(f"duplicate file {vf.rel_path}")
        seen.add(vf.rel_path.lower())
        out.append(vf)
    total = sum(len(v.content.encode()) for v in out)
    if total > MAX_TOTAL_BYTES:
        raise ValidationError(f"generated sources total {total} bytes (limit {MAX_TOTAL_BYTES})")
    return out


def validate_manifest(manifest: AppManifest) -> list[ValidatedFile]:
    files = _validate_files(manifest.files)
    entry = re.compile(r"@Composable\s+(?:internal\s+|public\s+)?fun\s+GenesisApp\s*\(\s*\)")
    if not any("/" not in f.rel_path and entry.search(f.content) for f in files):
        raise ValidationError("generated code must define `@Composable fun GenesisApp()` in package com.genesis.app")
    if not any(KIT_IMPORT_RE.search(f.content) for f in files):
        raise ValidationError("generated UI must be built with the Genesis design kit (import com.genesis.app.ui.kit.*)")
    return files


def validate_patch(patch: RepairPatch, current: dict[str, str]) -> list[ValidatedFile]:
    """A repair may only touch files that already exist in the generated set, plus a few new ones."""
    files = _validate_files(patch.files)
    new = [f.rel_path for f in files if f.rel_path not in current]
    if len(new) > 3:
        raise ValidationError(f"repair patch adds too many new files: {new}")
    merged = dict(current)
    merged.update({f.rel_path: f.content for f in files})
    if len(merged) > MAX_FILES:
        raise ValidationError("repair would exceed the file limit")
    if sum(len(c.encode()) for c in merged.values()) > MAX_TOTAL_BYTES:
        raise ValidationError("repair would exceed the total size limit")
    return files

