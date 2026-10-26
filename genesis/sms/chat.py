"""Genesis Chat: a mobile web chat (installable PWA) on the same conversation engine as SMS/WhatsApp.

Messages go through SmsService.handle exactly like a text message (same commands, projects, queue, worker,
Gemini + Gradle pipeline); replies are stored in SQLite and read back by the page. Access needs a one-time
link code (created on the Genesis computer), after which the browser holds an HttpOnly session cookie."""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from ..config import Settings
from ..core.jobs import JobStore
from . import messages as M
from .observe import event
from .service import Inbound, SmsService
from .store import SmsStore

STATIC = Path(__file__).resolve().parent.parent / "static" / "chat"
COOKIE = "genesis_chat"
SESSION_TTL_S = 30 * 86_400
LOCAL_OWNER = "web:" + "0" * 32  # the Genesis computer's own browser
CLIENT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
FILES = {"app.js": "text/javascript", "app.css": "text/css", "manifest.webmanifest": "application/manifest+json",
         "sw.js": "text/javascript", "icon.svg": "image/svg+xml"}
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


class AttemptLimiter:
    """Global cap on wrong link codes (behind a tunnel every client shares one IP, so it isn't per-IP)."""

    def __init__(self, max_failures: int = 20, window_s: float = 600):
        self.max, self.window = max_failures, window_s
        self.failures: deque[float] = deque()
        self.lock = threading.Lock()

    def blocked(self) -> bool:
        now = time.monotonic()
        with self.lock:
            while self.failures and now - self.failures[0] > self.window:
                self.failures.popleft()
            return len(self.failures) >= self.max

    def record(self) -> None:
        with self.lock:
            self.failures.append(time.monotonic())


def build_chat_router(settings: Settings, store: SmsStore, service: SmsService, builds: JobStore) -> APIRouter:
    r = APIRouter()
    limiter = AttemptLimiter()

    def secure(request: Request) -> bool:
        return (request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
                or settings.public_base_url.startswith("https://") and not getattr(request.state, "local", False))

    def current_user(request: Request) -> dict:
        token = request.cookies.get(COOKIE, "")
        user = store.web_session_user(token) if token else None
        if user is None:
            raise HTTPException(401, "Not signed in")
        return user

    def require_csrf(request: Request) -> None:
        # Cookies are SameSite=Strict; a custom header on top means no other site can post to the chat.
        if request.headers.get("x-genesis-chat") != "1":
            raise HTTPException(403, "missing chat header")

    def set_session(resp: JSONResponse, request: Request, user_id: int) -> JSONResponse:
        token = store.create_web_session(user_id, SESSION_TTL_S)
        resp.set_cookie(COOKIE, token, max_age=SESSION_TTL_S, httponly=True, samesite="strict",
                        secure=secure(request), path="/")
        return resp

    # ---------- page + assets (public: the page itself holds nothing) ----------
    @r.get("/chat")
    def chat_page():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache", "Content-Security-Policy": CSP})

    @r.get("/chat/")
    def chat_slash():
        return RedirectResponse("/chat", status_code=308)

    @r.get("/chat/{name}")
    def chat_asset(name: str):
        if name not in FILES:
            raise HTTPException(404, "Not found")
        headers = {"Cache-Control": "no-cache"}
        if name == "sw.js":
            headers["Service-Worker-Allowed"] = "/chat"
        return FileResponse(STATIC / name, media_type=FILES[name], headers=headers)

    # ---------- session ----------
    @r.post("/api/chat/session")
    async def sign_in(request: Request):
        require_csrf(request)
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(400, "body must be JSON") from None
        if not isinstance(data, dict):
            raise HTTPException(400, "body must be an object")
        if data.get("local") is True:
            # Only the browser on the Genesis computer itself (loopback, local Host, no proxy headers).
            if not getattr(request.state, "local", False):
                raise HTTPException(403, "Use a link code on this device")
            user = await run_in_threadpool(store.get_user, LOCAL_OWNER)
            if user is None:
                user = await run_in_threadpool(store.create_user, LOCAL_OWNER, "owner", "web")
            event("chat.signed_in", role="owner", local=True)
            return set_session(JSONResponse({"ok": True}), request, user["id"])
        code = str(data.get("code") or "")
        if limiter.blocked():
            event("chat.signin_blocked", logging.WARNING)
            raise HTTPException(429, "Too many wrong codes. Try again in a few minutes.")
        address = "web:" + secrets.token_hex(16)
        user = await run_in_threadpool(store.consume_link_code, code, address, "web") if code else None
        if user is None:
            limiter.record()
            event("chat.signin_failed", logging.WARNING)
            raise HTTPException(401, "That code is invalid or expired. Create a new one on the Weave computer.")
        event("chat.signed_in", role=user["role"])
        return set_session(JSONResponse({"ok": True}), request, user["id"])

    @r.post("/api/chat/logout")
    def sign_out(request: Request):
        require_csrf(request)
        token = request.cookies.get(COOKIE, "")
        if token:
            store.delete_web_session(token)
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    # ---------- conversation ----------
    @r.get("/api/chat/state")
    def state(request: Request, after: int = 0):
        """New messages since `after`, plus the live state of the user's current build (from the build store)."""
        user = current_user(request)
        msgs = [{"id": m["id"], "from": "me" if m["direction"] == "in" else "genesis",
                 "text": m["body"] if m["direction"] == "in" else m["body"].removeprefix("Genesis: ").removeprefix("Weave: "),
                 "at": m["created_at"]} for m in store.messages_for_user(user["id"], max(0, after))]
        job = store.active_job(user["id"])
        project = store.project(user["id"], user["active_project_id"])
        if job is None and project is not None:
            job = store.latest_job(user["id"], project["id"])
        build = None
        if job is not None:
            build = {"ref": job["ref"], "status": job["status"], "kind": job["kind"], "stage": None,
                     "progress": None, "label": None, "project": M.name_of(store.project(user["id"], job["project_id"]))}
            job_project = store.project(user["id"], job["project_id"]) or {}
            website = job_project.get("kind") == "website"
            if job["status"] == "running" and job["build_id"] and job["kind"] != "publish":
                b = service.build_record(job["build_id"], "website" if website else "android")
                if b is not None:
                    table = M.WEB_PROGRESS if website else M.PROGRESS
                    build.update(stage=b.get("stage"), progress=b.get("progress"),
                                 label=table.get(b.get("stage", ""), (None, None, b.get("message")))[2])
        projects = [{"number": p["number"], "name": M.name_of(p), "active": p["id"] == user["active_project_id"],
                     "ready": bool(p["last_success_build_id"]), "kind": p.get("kind") or "android",
                     "published": bool(p.get("deploy_url"))} for p in store.projects(user["id"])]
        return {"messages": msgs, "build": build, "projects": projects}

    @r.post("/api/chat/messages")
    async def send(request: Request):
        require_csrf(request)
        user = await run_in_threadpool(current_user, request)
        try:
            data = await request.json()
        except ValueError:
            raise HTTPException(400, "body must be JSON") from None
        text = str((data or {}).get("text") or "").strip()
        client_id = str((data or {}).get("client_id") or "")
        if not text or len(text) > 1600:
            raise HTTPException(422, "Message must be 1-1600 characters")
        if not CLIENT_ID_RE.fullmatch(client_id):
            raise HTTPException(422, "client_id must be 32 hex characters")
        # client_id makes retries of the same send idempotent, like Twilio's MessageSid.
        outcome = await run_in_threadpool(service.handle, Inbound(from_=user["phone"], to="web", body=text,
                                                                   sid="WB" + client_id))
        event("chat.message", outcome=outcome)
        return {"outcome": outcome}

    return r
