"""Publishing a generated website to Netlify. Runs only after the owner explicitly approves (see SmsService).

Uses the Netlify REST API with NETLIFY_AUTH_TOKEN in the Authorization header only. weave's netlifyDeployer is
deliberately not used: it passes the token on the command line and silently falls back to anonymous, public
Netlify Drop deploys. Here there is no anonymous path: without a token, nothing is published."""

from __future__ import annotations

import io
import json
import re
import secrets
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

API = "https://api.netlify.com/api/v1"


class PublishError(RuntimeError):
    """Safe to show to the user; never contains the token."""


# (method, url, body, headers) -> (status, json-or-None)
Http = Callable[[str, str, bytes | None, dict], tuple[int, dict | None]]


def _http(method: str, url: str, body: bytes | None, headers: dict) -> tuple[int, dict | None]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed https API host
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except json.JSONDecodeError:
            return e.code, None
    except urllib.error.URLError as e:
        raise PublishError(f"Could not reach Netlify: {e.reason}") from None


def zip_site(site_dir: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(site_dir.iterdir()):
            if p.is_file() and not p.is_symlink():
                z.write(p, p.name)
    return buf.getvalue()


def site_name(brand: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (brand or "site").lower()).strip("-")[:30] or "site"
    return f"genesis-{slug}-{secrets.token_hex(3)}"


def publish(token: str, site_dir: Path, *, brand: str, site_id: str | None, http: Http = _http,
            poll_s: float = 2.0, timeout_s: float = 120) -> dict:
    """Deploy site_dir. Creates a site on the first publish, then updates the same site. Returns {site_id, url, deploy_id}."""
    if not token:
        raise PublishError("Publishing is not configured (NETLIFY_AUTH_TOKEN is missing)")
    if not (site_dir / "index.html").is_file():
        raise PublishError("There is no website to publish")
    auth = {"Authorization": f"Bearer {token}", "User-Agent": "Genesis"}

    def check(status: int, data: dict | None, what: str) -> dict:
        if status in (401, 403):
            raise PublishError("Netlify rejected the token (check NETLIFY_AUTH_TOKEN)")
        if status == 429:
            raise PublishError("Netlify rate limit reached; try again later")
        if status >= 400 or not isinstance(data, dict):
            msg = (data or {}).get("message") if isinstance(data, dict) else None
            raise PublishError(f"Netlify {what} failed (HTTP {status}{': ' + str(msg)[:200] if msg else ''})")
        return data

    if not site_id:
        site = check(*http("POST", f"{API}/sites", json.dumps({"name": site_name(brand)}).encode(),
                           {**auth, "Content-Type": "application/json"}), "site creation")
        site_id = site.get("id")
        if not site_id:
            raise PublishError("Netlify did not return a site id")
    deploy = check(*http("POST", f"{API}/sites/{site_id}/deploys", zip_site(site_dir),
                         {**auth, "Content-Type": "application/zip"}), "deploy")
    deploy_id = deploy.get("id")
    deadline = time.monotonic() + timeout_s
    while deploy.get("state") not in ("ready", "error"):
        if time.monotonic() > deadline:
            raise PublishError("Netlify did not finish the deploy in time")
        time.sleep(poll_s)
        deploy = check(*http("GET", f"{API}/deploys/{deploy_id}", None, auth), "deploy status")
    if deploy.get("state") != "ready":
        raise PublishError(f"Netlify deploy failed: {str(deploy.get('error_message') or 'unknown error')[:200]}")
    url = deploy.get("ssl_url") or deploy.get("url")
    if not url or not str(url).startswith("https://"):
        raise PublishError("Netlify did not return a site URL")
    return {"site_id": site_id, "url": url, "deploy_id": deploy_id}
