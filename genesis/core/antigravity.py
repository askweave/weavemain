"""Antigravity bridge: generate apps through the Antigravity desktop app's agent instead of the Gemini API.

Genesis starts a conversation with Antigravity's own `agentapi` command and reads the agent's reply from
the transcript Antigravity writes under ~/.gemini/antigravity/brain/<conversation>/. Requests then run on
the model and quota of the Google account signed in to Antigravity; no GEMINI_API_KEY is used.

`agentapi` only talks to a running Antigravity, and only when ANTIGRAVITY_LS_ADDRESS and
ANTIGRAVITY_CSRF_TOKEN are set. Antigravity sets both in its own terminals, so start Genesis from a
terminal inside Antigravity. Genesis never looks the token up anywhere else and never logs it.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, ValidationError as PydanticValidationError

from ..config import Settings
from . import prompts
from .gemini import GeminiError, _compact_validation_error, _strip_fences
from .schemas import AppManifest, RepairPatch

log = logging.getLogger("genesis.antigravity")

ENV_VARS = ("ANTIGRAVITY_LS_ADDRESS", "ANTIGRAVITY_CSRF_TOKEN")
DEFAULT_EXE = Path.home() / ".gemini" / "antigravity" / "bin" / ("agentapi.bat" if sys.platform == "win32" else "agentapi")
BRAIN_DIR = Path.home() / ".gemini" / "antigravity" / "brain"
TIERS = ("app", "flash_lite", "flash", "pro")
POLL_S = 2.0
DIRECT_TIMEOUT_S = 45  # a long prompt passed straight to agentapi may never start a conversation
START_TIMEOUT_S = 120
# Long requests go through a file here instead (Antigravity's own scratch area, readable by its agent).
REQUEST_DIR = Path.home() / ".gemini" / "antigravity" / "scratch" / "genesis-requests"
SETTLE_S = 20.0  # after an unusable reply, how long to wait for the agent to send a better one

INSTRUCTIONS = """You are being called by the Genesis app builder as a pure text generator.
Do NOT use any tools (other than reading the request file you were pointed to, if any): do not create or
edit files, do not run commands, do not browse.
Reply with ONE JSON object and nothing else (no prose, no markdown fences). It must validate against
this JSON Schema:
"""


class _NoStart(Exception):
    """agentapi did not create a conversation in time."""


class AntigravityClient:
    """Same interface as GeminiClient (generate_app / modify_app / repair / model_name / configured)."""

    def __init__(self, settings: Settings, *, exe: Path | None = None, brain_dir: Path | None = None,
                 request_dir: Path | None = None):
        self.s = settings
        self.exe = exe or Path(os.environ.get("ANTIGRAVITY_AGENTAPI_EXE") or DEFAULT_EXE)
        self.brain_dir = brain_dir or BRAIN_DIR
        self.request_dir = request_dir or REQUEST_DIR
        self.file_mode = False  # switched on for good once a direct prompt fails to start a conversation
        self._cut_off = False  # the last reply hit Antigravity's output limit

    @property
    def configured(self) -> bool:
        return all(os.environ.get(v) for v in ENV_VARS) and self.exe.exists()

    def problem(self) -> str:
        if not self.exe.exists():
            return f"Antigravity's agentapi was not found at {self.exe}. Install/open Antigravity first."
        if not all(os.environ.get(v) for v in ENV_VARS):
            return ("Genesis is not running inside an Antigravity terminal (ANTIGRAVITY_LS_ADDRESS is not set). "
                    "Open Antigravity, open its terminal, and start Genesis from there.")
        return ""

    def model_name(self) -> str:
        if not self.configured:
            raise GeminiError(self.problem())
        tier = self.s.antigravity_model
        return "antigravity (model selected in the app)" if tier == "app" else f"antigravity:{tier}"

    # ---------- calls ----------
    def generate_app(self, prompt: str, app_name: str | None) -> tuple[AppManifest, dict]:
        return self._structured(prompts.generation_prompt(prompt, app_name), AppManifest, "Genesis: new app")

    def modify_app(self, change: str, files: dict[str, str], manifest: AppManifest) -> tuple[AppManifest, dict]:
        return self._structured(prompts.modification_prompt(change, files, manifest), AppManifest, "Genesis: change")

    def repair(self, diagnostics: str, files: dict[str, str], manifest: AppManifest) -> tuple[RepairPatch, dict]:
        return self._structured(prompts.repair_prompt(diagnostics, files, manifest), RepairPatch, "Genesis: fix build")

    def ask(self, system: str, user: str, schema: type[BaseModel], title: str = "Genesis chat",
            timeout: int | None = None) -> tuple[BaseModel, dict]:
        """One structured request with a custom system prompt (used by the chat brain)."""
        return self._structured(user, schema, title, system=system, timeout=timeout)

    def _structured(self, user: str, schema: type[BaseModel], title: str, attempts: int = 2,
                    system: str = prompts.SYSTEM, timeout: int | None = None):
        if not self.configured:
            raise GeminiError(self.problem())
        base = (f"{system}\n\n{user}\n\n{INSTRUCTIONS}"
                f"{json.dumps(schema.model_json_schema(), separators=(',', ':'))}")
        last_err = ""
        for attempt in range(1, attempts + 1):
            text = base if attempt == 1 else (
                f"{base}\n\nA previous reply was rejected: {last_err}\nReturn ONLY valid JSON matching the schema.")
            started = time.monotonic()
            conv = self._start(text, title)
            log.info("Antigravity conversation %s started (attempt %s)", conv, attempt)
            self._cut_off = False
            replies = self._wait(conv, started, timeout or self.s.antigravity_timeout)
            meta = {"model": self.model_name(), "seconds": round(time.monotonic() - started, 1),
                    "attempt": attempt, "conversation": conv}
            for reply in reversed(replies):
                try:
                    return schema.model_validate_json(_extract_json(reply)), meta
                except PydanticValidationError as e:
                    last_err = _compact_validation_error(e)
                except (json.JSONDecodeError, ValueError) as e:
                    last_err = f"invalid JSON: {e}"
            if self._cut_off:
                last_err = ("your reply was cut off because it was too long. Write a smaller app: well under "
                            "30,000 characters of code in total, split into several files")
            elif not replies:
                last_err = "no reply"
            log.warning("Antigravity reply unusable (attempt %s): %s", attempt, last_err)
        raise GeminiError(f"Antigravity did not return a valid {schema.__name__}: {last_err}")

    def _start(self, prompt: str, title: str) -> str:
        if not self.file_mode:
            try:
                return self._launch(prompt, title, DIRECT_TIMEOUT_S)
            except _NoStart:
                log.warning("Antigravity did not start a conversation for a %s-char prompt; using a request file",
                            len(prompt))
                self.file_mode = True
        path = self._write_request(prompt)
        short = (f"Read the file {path} in full (it is long; read every part). It is a request from the Genesis "
                 "app builder. Follow its instructions exactly and reply with only the JSON object it asks for.")
        try:
            return self._launch(short, title, START_TIMEOUT_S)
        except _NoStart:
            raise GeminiError(f"Antigravity did not start a conversation within {START_TIMEOUT_S}s. "
                              "Is Antigravity open, signed in, and not showing a prompt?") from None

    def _write_request(self, prompt: str) -> Path:
        self.request_dir.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - 86400
        for old in self.request_dir.glob("*.md"):
            try:
                if old.stat().st_mtime < cutoff:
                    old.unlink()
            except OSError:
                pass
        path = self.request_dir / f"{uuid.uuid4().hex}.md"
        path.write_text(prompt, encoding="utf-8")
        return path

    def base_cmd(self) -> list[str]:
        # Inside Antigravity, ANTIGRAVITY_AGENTAPI_EXE is the language_server binary itself, which needs the
        # "agentapi" subcommand (the ~/.gemini/.../bin/agentapi shim adds it). Without it a second language
        # server starts and never answers.
        name = self.exe.name.lower()
        is_agentapi = name in ("agentapi", "agentapi.bat", "agentapi.exe", "agentapi.cmd")
        args = [] if is_agentapi else ["agentapi"]
        if sys.platform == "win32":
            if name.endswith((".bat", ".cmd")):
                return ["cmd.exe", "/c", str(self.exe), *args]
            if name.endswith(".py"):
                return [sys.executable, str(self.exe), *args]
            if self.exe.is_file() and not name.endswith(".exe"):
                try:
                    with open(self.exe, "rb") as f:
                        header = f.read(128)
                        if header.startswith(b"#!") and b"python" in header:
                            return [sys.executable, str(self.exe), *args]
                except OSError:
                    pass
        return [str(self.exe), *args]

    def _launch(self, prompt: str, title: str, timeout: float) -> str:
        tag = uuid.uuid4().hex
        prompt = f"{prompt}\n\n(Genesis request {tag})"
        cmd = [*self.base_cmd(), "new-conversation", f"--title={title}"]
        if self.s.antigravity_model != "app":
            cmd.append(f"--model={self.s.antigravity_model}")
        # Only what agentapi needs. Inheriting the parent agent's conversation/trajectory variables (Genesis is
        # often started by an Antigravity agent) could tie the request to that busy conversation.
        env = {k: v for k, v in os.environ.items() if not k.startswith("ANTIGRAVITY_")}
        env.update({v: os.environ[v] for v in ENV_VARS})
        # Keep Genesis conversations out of the user's Antigravity projects (and their files).
        env["ANTIGRAVITY_PROJECT_ID"] = self.s.antigravity_project
        since = time.time() - 5
        try:
            proc = subprocess.Popen([*cmd, "--", prompt], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, start_new_session=True)
        except OSError as e:
            raise GeminiError(f"Could not start Antigravity's agentapi: {type(e).__name__}") from e
        deadline = time.monotonic() + timeout
        out = err = ""
        while True:
            try:
                out, err = proc.communicate(timeout=POLL_S)
                break
            except subprocess.TimeoutExpired:
                conv = self._find_by_tag(tag, since)  # the command may be slow to return after starting it
                if conv or time.monotonic() > deadline:
                    proc.kill()
                    proc.communicate()
                    if conv:
                        return conv
                    raise _NoStart() from None
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            data = {}
        conv = ((data.get("response") or {}).get("newConversation") or {}).get("conversationId")
        if not conv:
            msg = str(data.get("error") or err or out or "no conversation id").strip()[:300]
            hint = " Is Antigravity open and signed in?" if "connection" in msg.lower() else ""
            raise GeminiError(f"Antigravity refused the request: {msg}.{hint}")
        return conv

    def _find_by_tag(self, tag: str, since: float) -> str | None:
        try:
            dirs = [d for d in self.brain_dir.iterdir() if d.is_dir() and d.stat().st_mtime >= since]
        except OSError:
            return None
        for d in dirs:
            steps = _read_steps(d / ".system_generated" / "logs" / "transcript_full.jsonl")
            if steps and tag in (steps[0].get("content") or ""):
                return d.name
        return None

    def _wait(self, conv: str, started: float, timeout: int) -> list[str]:
        """Poll the transcript until the agent has replied and gone quiet, or the timeout passes."""
        path = self.brain_dir / conv / ".system_generated" / "logs" / "transcript_full.jsonl"
        deadline = started + timeout
        replies: list[str] = []
        last_change = time.monotonic()
        seen = 0
        while time.monotonic() < deadline:
            steps = _read_steps(path)
            if len(steps) != seen:
                seen, last_change = len(steps), time.monotonic()
                if any(st.get("type") == "ERROR_MESSAGE" and "token limit" in (st.get("content") or "")
                       for st in steps):
                    self._cut_off = True  # Antigravity truncated the reply; waiting longer won't fix it
                    return [st["content"] for st in steps if st.get("type") == "PLANNER_RESPONSE"
                            and (st.get("content") or "").strip()]
                replies = [st["content"] for st in steps if st.get("type") == "PLANNER_RESPONSE"
                           and st.get("status") == "DONE" and (st.get("content") or "").strip()]
                if replies and _looks_complete(replies[-1]):
                    return replies
            if replies and time.monotonic() - last_change > SETTLE_S:
                return replies
            time.sleep(POLL_S)
        if replies:
            return replies
        raise GeminiError(f"Antigravity did not answer within {timeout}s "
                          f"(conversation {conv}). Check the Antigravity window for a prompt or quota message.")


def _read_steps(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    steps = []
    for line in lines:
        try:
            steps.append(json.loads(line))
        except json.JSONDecodeError:
            break  # a line still being written
    return steps


def _extract_json(text: str) -> str:
    text = _strip_fences(text.strip())
    if text.startswith("{"):
        return text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    return text[start:end + 1]


def _looks_complete(text: str) -> bool:
    try:
        json.loads(_extract_json(text))
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def diagnose(settings: Settings) -> int:
    """Run agentapi directly with a tiny and a full-size prompt and print what it says (never the token)."""
    client = AntigravityClient(settings)
    print(f"agentapi: {client.exe} ({'found' if client.exe.exists() else 'MISSING'})")
    for v in (*ENV_VARS, "ANTIGRAVITY_CONVERSATION_ID", "ANTIGRAVITY_TRAJECTORY_ID", "ANTIGRAVITY_AGENT"):
        print(f"{v}: {'set' if os.environ.get(v) else 'not set'}")
    if not client.configured:
        print(client.problem())
        return 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTIGRAVITY_")}
    env.update({v: os.environ[v] for v in ENV_VARS})
    env["ANTIGRAVITY_PROJECT_ID"] = settings.antigravity_project
    big = f"{prompts.SYSTEM}\n\n{prompts.generation_prompt('A simple counter app', None)}\n\n{INSTRUCTIONS}" + \
        json.dumps(AppManifest.model_json_schema(), separators=(",", ":"))
    ok = True
    for name, prompt in (("tiny", "Reply with the single word OK. Do not use tools."), ("full-size", big)):
        started = time.monotonic()
        try:
            r = subprocess.run([*client.base_cmd(), "new-conversation", f"--title=Genesis check: {name}", "--", prompt],
                               env=env, capture_output=True, text=True, timeout=45)
            result = (r.stdout or r.stderr).strip().replace("\n", " ")[:400]
        except subprocess.TimeoutExpired as e:
            ok = False
            partial = ((e.stdout or b"") + (e.stderr or b"")).decode(errors="replace").strip()[:400]
            result = f"NO ANSWER after 45s. Partial output: {partial or '(none)'}"
        print(f"{name} prompt ({len(prompt):,} chars, {time.monotonic() - started:.1f}s): {result}")
    return 0 if ok else 1


def make_ai_client(settings: Settings):
    if settings.ai_backend == "antigravity":
        return AntigravityClient(settings)
    from .gemini import GeminiClient
    return GeminiClient(settings)
