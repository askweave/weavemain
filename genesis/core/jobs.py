"""Build jobs: persistence, queueing, and the generate -> validate -> build -> repair pipeline."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import ValidationError as PydanticValidationError

from ..config import Settings
from .builder import AndroidBuilder, BuildError
from .diagnostics import errors_only, failure_summary, parse_diagnostics
from .gemini import GeminiError
from .schemas import AppManifest, BuildRequest, RepairPatch
from .validation import ValidationError, validate_manifest, validate_patch

log = logging.getLogger("genesis.jobs")

JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
TERMINAL = {"succeeded", "failed"}
STAGE_PROGRESS = {"queued": 2, "generating": 15, "validating": 35, "building": 50, "repairing": 70, "verifying": 92,
                  "succeeded": 100, "failed": 100}


class Generator(Protocol):
    def generate_app(self, prompt: str, app_name: str | None) -> tuple[AppManifest, dict]: ...
    def repair(self, diagnostics: str, files: dict[str, str], manifest: AppManifest) -> tuple[RepairPatch, dict]: ...
    # Optional: generators without modify_app cannot run change builds.
    # def modify_app(self, change: str, files: dict[str, str], manifest: AppManifest) -> tuple[AppManifest, dict]: ...


# Called with (job, event) on every stage change and when the build ends. Must not raise.
Listener = Callable[[dict, str], None]


class QueueFullError(RuntimeError):
    pass


class JobCancelled(Exception):
    pass


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False
    return True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:40] or "app"


class JobStore:
    """One directory per build: data/builds/<id>/{job.json, build.log, manifest.json, workspace/, artifact/}."""

    def __init__(self, builds_dir: Path):
        self.dir = builds_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def path(self, job_id: str) -> Path:
        if not JOB_ID_RE.fullmatch(job_id or ""):
            raise KeyError(job_id)
        return self.dir / job_id

    def create(self, req: BuildRequest, *, base_job_id: str | None = None, change_request: str | None = None,
               source: str = "dashboard") -> dict:
        job_id = uuid.uuid4().hex
        d = self.path(job_id)
        d.mkdir(parents=False, exist_ok=False)
        job = {
            "id": job_id, "created_at": now_iso(), "updated_at": now_iso(),
            "prompt": req.prompt, "requested_name": req.app_name,
            "status": "queued", "stage": "queued", "progress": STAGE_PROGRESS["queued"],
            "message": "Waiting for a build slot", "app_name": req.app_name, "package_id": None,
            "category": None, "primary_color": None, "description": None, "features": [], "validation_rules": [],
            "attempts": [], "apk": None, "error": None, "ai_calls": [],
            "source": source, "base_job_id": base_job_id, "change_request": change_request,
            "cancelled": False, "owner_pid": os.getpid(),
        }
        self.save(job)
        return job

    def save(self, job: dict) -> None:
        with self._lock:
            job["updated_at"] = now_iso()
            p = self.path(job["id"]) / "job.json"
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(job, indent=2), encoding="utf-8")
            tmp.replace(p)

    def get(self, job_id: str) -> dict:
        p = self.path(job_id) / "job.json"
        with self._lock:
            if not p.is_file():
                raise KeyError(job_id)
            return json.loads(p.read_text(encoding="utf-8"))

    def list(self, limit: int = 50) -> list[dict]:
        jobs = []
        for p in self.dir.glob("*/job.json"):
            try:
                jobs.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
        return jobs[:limit]

    def log_path(self, job_id: str) -> Path:
        return self.path(job_id) / "build.log"

    def mark_interrupted(self) -> None:
        """Fail unfinished builds whose owning process is gone (or is this process, i.e. a restart).
        Builds owned by another live process (e.g. a separate SMS worker) are left alone."""
        me = os.getpid()
        for job in self.list(limit=10_000):
            owner = job.get("owner_pid")
            if job.get("status") not in TERMINAL and (owner == me or not _pid_alive(owner)):
                job.update(status="failed", stage="failed", progress=100,
                           message="Interrupted: the Genesis server restarted during this build",
                           error="Interrupted by server restart")
                self.save(job)


class Orchestrator:
    def __init__(self, settings: Settings, generator: Generator, builder: AndroidBuilder | None = None,
                 store: JobStore | None = None):
        self.s = settings
        self.gen = generator
        self.builder = builder or AndroidBuilder(settings)
        self.store = store or JobStore(settings.builds_dir)
        self.pool = ThreadPoolExecutor(max_workers=settings.max_concurrent_builds, thread_name_prefix="genesis-build")
        self._active = 0
        self._active_lock = threading.Lock()
        # Shared by dashboard builds and SMS builds run in this process, so the Gradle limit holds for both.
        self._slots = threading.BoundedSemaphore(settings.max_concurrent_builds)
        self._cancel: dict[str, threading.Event] = {}
        self._listeners: dict[str, Listener] = {}
        self.store.mark_interrupted()

    # ---------- public ----------
    def submit(self, req: BuildRequest) -> dict:
        with self._active_lock:
            if self._active >= self.s.max_queued_builds:
                raise QueueFullError(f"{self._active} builds are already queued or running; try again shortly")
            self._active += 1
        job = self.store.create(req)
        self.pool.submit(self._run_safely, job["id"])
        return job

    def run_sync(self, req: BuildRequest) -> dict:
        """Used by the CLI and tests."""
        job = self.store.create(req)
        return self.run_existing(job["id"])

    def create_job(self, req: BuildRequest, *, base_job_id: str | None = None, change_request: str | None = None,
                   source: str = "dashboard") -> dict:
        """Create a queued build record without running it (the SMS worker runs it with run_existing)."""
        if base_job_id is not None:
            base = self.store.get(base_job_id)  # KeyError if unknown
            if base.get("status") != "succeeded":
                raise ValueError("a change build needs a successful base build")
        return self.store.create(req, base_job_id=base_job_id, change_request=change_request, source=source)

    def run_existing(self, job_id: str, listener: Listener | None = None) -> dict:
        """Run a created build in the calling thread, waiting for a free build slot first."""
        with self._active_lock:
            self._active += 1
        if listener:
            self._listeners[job_id] = listener
        self._cancel.setdefault(job_id, threading.Event())
        self._run_safely(job_id)
        return self.store.get(job_id)

    def cancel(self, job_id: str) -> bool:
        """Request cancellation of a build running in this process. Returns False if it is not running here."""
        ev = self._cancel.get(job_id)
        if ev is None:
            return False
        ev.set()
        return True

    # ---------- pipeline ----------
    def _run_safely(self, job_id: str) -> None:
        cancel = self._cancel.setdefault(job_id, threading.Event())
        try:
            with self._slots:
                job = self.store.get(job_id)
                job["owner_pid"] = os.getpid()
                try:
                    if cancel.is_set():
                        raise JobCancelled()
                    self._run(job)
                except JobCancelled:
                    job = self.store.get(job_id)
                    job["cancelled"] = True
                    self._fail(job, "Cancelled by user")
                except Exception as e:  # noqa: BLE001 - every failure must be reported, never swallowed
                    log.exception("build %s crashed", job_id)
                    job = self.store.get(job_id)
                    self._log(job, f"!! Internal error: {type(e).__name__}: {e}")
                    self._fail(job, f"Internal error: {type(e).__name__}: {e}")
        finally:
            with self._active_lock:
                self._active -= 1
            self._cancel.pop(job_id, None)
            self._listeners.pop(job_id, None)

    def _generate(self, job: dict, req: BuildRequest, feedback: str) -> tuple[AppManifest, dict]:
        """New app from the prompt, or a modified version of the base build's app for change builds."""
        base_id = job.get("base_job_id")
        if not base_id:
            return self.gen.generate_app(req.prompt + feedback, req.app_name)
        modify = getattr(self.gen, "modify_app", None)
        if modify is None:
            raise GeminiError("This generator cannot modify existing apps")
        base_dir = self.store.path(base_id)
        base_manifest = AppManifest.model_validate_json((base_dir / "manifest.json").read_text(encoding="utf-8"))
        sources = self.builder.read_sources(base_dir / "workspace")
        if not sources:
            raise GeminiError("The sources of the previous build are no longer available")
        manifest, meta = modify((job.get("change_request") or req.prompt) + feedback, sources, base_manifest)
        # Same applicationId and debug key, so the new APK installs as an update over the old one.
        manifest.package_id = base_manifest.package_id
        return manifest, meta

    def _run(self, job: dict) -> None:
        req = BuildRequest(prompt=job["prompt"], app_name=job["requested_name"])
        doctor = self.s.doctor()
        missing = [c for c in doctor["checks"] if not c["ok"]]
        if missing:
            lines = [f"- {c['name']}: {c['detail']}. Fix: {c['fix']}" for c in missing]
            self._log(job, "Prerequisites missing:\n" + "\n".join(lines))
            return self._fail(job, "Prerequisites missing: " + ", ".join(c["name"] for c in missing))

        # 1. Generate + validate (one regeneration if the output breaks a safety/structure rule).
        manifest, files = None, None
        feedback = ""
        for gen_try in (1, 2):
            changing = bool(job.get("base_job_id"))
            self._stage(job, "generating", ("Gemini is applying your changes" if changing else "Gemini is designing your app")
                        if gen_try == 1 else "Regenerating after validation failure")
            self._log(job, f"== {'Modifying' if changing else 'Generating'} app with Gemini (try {gen_try}) ==")
            try:
                manifest, meta = self._generate(job, req, feedback)
            except (GeminiError, OSError, KeyError, PydanticValidationError) as e:
                self._log(job, f"!! {e}")
                return self._fail(job, str(e))
            job["ai_calls"].append({"kind": "modify" if changing else "generate", **meta})
            if req.app_name:
                manifest.app_name = req.app_name
            self._stage(job, "validating", "Validating generated sources")
            try:
                files = validate_manifest(manifest)
                break
            except ValidationError as e:
                self._log(job, f"!! Generated output rejected: {e}")
                feedback = (f"\n\n(A previous attempt was rejected by the Genesis validator: {e}. "
                            "Follow the template contract exactly.)")
                files = None
        if files is None or manifest is None:
            return self._fail(job, "Generated code failed validation twice; see log")

        job.update(app_name=manifest.app_name, package_id=manifest.package_id, category=manifest.category.value,
                   primary_color=manifest.primary_color,
                   description=manifest.description, features=manifest.features,
                   validation_rules=manifest.validation_rules)
        self._log(job, f"App: {manifest.app_name} ({manifest.package_id}), category {manifest.category.value}")
        self._log(job, "Files: " + ", ".join(f.rel_path for f in files))
        self.store.save(job)
        (self.store.path(job["id"]) / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

        # 2. Workspace
        workspace = self.store.path(job["id"]) / "workspace"
        try:
            self.builder.prepare_workspace(workspace, manifest)
            self.builder.write_sources(workspace, files)
        except (BuildError, ValidationError, OSError) as e:
            self._log(job, f"!! Workspace setup failed: {e}")
            return self._fail(job, f"Workspace setup failed: {e}")

        # 3. Build with bounded repair.
        try:
            self._build_loop(job, manifest, workspace)
        finally:
            try:
                self.builder.cleanup_workspace(workspace)
            except Exception as e:  # noqa: BLE001
                log.warning("cleanup failed for %s: %s", job["id"], e)

    def _build_loop(self, job: dict, manifest: AppManifest, workspace: Path) -> None:
        max_attempts = 1 + self.s.max_repairs
        for n in range(1, max_attempts + 1):
            kind = "initial" if n == 1 else "repair"
            self._stage(job, "building", f"Compiling with Gradle (attempt {n} of {max_attempts})")
            self._log(job, f"== Gradle build, attempt {n}/{max_attempts} ==")
            result = self.builder.run_gradle(workspace, self.store.log_path(job["id"]), cancel=self._cancel.get(job["id"]))
            if result.cancelled:
                raise JobCancelled()
            diags = parse_diagnostics(result.output)
            errs = errors_only(diags)
            attempt = {"n": n, "kind": kind, "exit_code": result.exit_code, "seconds": round(result.seconds, 1),
                       "timed_out": result.timed_out, "errors": [d.render() for d in errs[:20]]}
            job["attempts"].append(attempt)
            self.store.save(job)

            if result.ok:
                self._stage(job, "verifying", "Verifying APK")
                try:
                    info = self.builder.verify_apk(workspace, manifest.package_id)
                except BuildError as e:
                    self._log(job, f"!! APK verification failed: {e}")
                    return self._fail(job, f"Gradle succeeded but APK verification failed: {e}")
                artifact_dir = self.store.path(job["id"]) / "artifact"
                artifact_dir.mkdir(exist_ok=True)
                filename = f"{slugify(manifest.app_name)}-{job['id'][:8]}.apk"
                shutil.copy2(info.path, artifact_dir / filename)
                for c in info.checks:
                    self._log(job, f"✓ {c}")
                job["apk"] = {"filename": filename, "size": info.size, "package": info.package, "checks": info.checks}
                self._log(job, f"== SUCCESS: {filename} ==")
                job.update(status="succeeded", stage="succeeded", progress=100,
                           message=f"APK ready ({info.size / 1_048_576:.1f} MB)", error=None)
                self.store.save(job)
                self._notify(job, "succeeded")
                return

            if result.timed_out:
                return self._fail(job, f"Build timed out after {self.s.build_timeout}s")
            generated_errs = [d for d in errs if d.rel_path is not None]
            if not generated_errs:
                summary = failure_summary(result.output)
                self._log(job, "!! Build failed outside generated code (toolchain/template); not sending to AI repair.")
                return self._fail(job, "Build failed outside generated code:\n" + summary)
            if n == max_attempts:
                return self._fail(job, f"Compilation still failing after {self.s.max_repairs} repair attempt(s): "
                                       f"{len(generated_errs)} error(s); see log")

            # Repair
            self._stage(job, "repairing", f"Asking Gemini to fix {len(generated_errs)} compiler error(s)")
            diag_text = "\n".join(d.render() for d in generated_errs[:25])
            current = self.builder.read_sources(workspace)
            affected = {d.rel_path for d in generated_errs}
            # Send affected files first; include the rest for context while it stays small.
            ordered = {p: current[p] for p in sorted(current, key=lambda p: p not in affected)}
            try:
                patch, meta = self.gen.repair(diag_text, ordered, manifest)
                job["ai_calls"].append({"kind": "repair", **meta})
                patched = validate_patch(patch, current)
                self.builder.write_sources(workspace, patched)
            except (GeminiError, ValidationError) as e:
                self._log(job, f"!! Repair rejected: {e}")
                return self._fail(job, f"Automatic repair failed: {e}")
            attempt["patch"] = {"explanation": patch.explanation[:500], "files": [f.rel_path for f in patched]}
            self._log(job, f"Repair patch: {patch.explanation[:300]} (files: {', '.join(f.rel_path for f in patched)})")
            self.store.save(job)

    # ---------- helpers ----------
    def _stage(self, job: dict, stage: str, message: str) -> None:
        ev = self._cancel.get(job["id"])
        if ev is not None and ev.is_set():
            raise JobCancelled()
        job.update(status=stage if stage in TERMINAL else "running", stage=stage,
                   progress=STAGE_PROGRESS.get(stage, job.get("progress", 0)), message=message)
        self.store.save(job)
        self._notify(job, stage)

    def _fail(self, job: dict, error: str) -> None:
        job.update(status="failed", stage="failed", progress=100,
                   message="Build cancelled" if job.get("cancelled") else "Build failed", error=error[:4000])
        self._log(job, f"== FAILED: {error[:500]} ==")
        self.store.save(job)
        self._notify(job, "failed")

    def _notify(self, job: dict, event: str) -> None:
        listener = self._listeners.get(job["id"])
        if listener is None:
            return
        try:
            listener(dict(job), event)
        except Exception:  # noqa: BLE001 - a notification problem must never break a build
            log.exception("build listener failed for %s", job["id"])

    def _log(self, job: dict, line: str) -> None:
        with open(self.store.log_path(job["id"]), "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {line}\n")


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    """Shape for the API (no filesystem paths)."""
    keys = ["id", "created_at", "updated_at", "prompt", "status", "stage", "progress", "message", "app_name",
            "package_id", "category", "primary_color", "description", "features", "validation_rules", "attempts", "apk", "error",
            "ai_calls", "source", "base_job_id", "cancelled"]
    return {k: job.get(k) for k in keys}
