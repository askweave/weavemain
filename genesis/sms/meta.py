"""Meta WhatsApp Cloud API transport, payload parsing, and cryptographic verification.

Provides Graph API v21+ messaging, media retrieval, HMAC-SHA256 webhook validation,
and normalized event parsing for the Weave backend.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

import httpx

from ..config import Settings

log = logging.getLogger("genesis.sms.meta")

GRAPH_API_BASE = "https://graph.facebook.com"
DEFAULT_GRAPH_VERSION = "v21.0"
MAX_MEDIA_BYTES = 16 * 1024 * 1024  # 16 MB WhatsApp limit

# Permanent error codes from Meta Cloud API documentation:
# 100: Invalid parameter
# 131030: Recipient phone number not in allowed list (Sandbox/dev restriction)
# 131047: Re-engagement message failed (outside 24h customer service window)
# 131026: Message undeliverable
# 131051: Unsupported message type
# 190: Access token expired / invalid
PERMANENT_META_CODES = {100, 190, 131026, 131030, 131047, 131051}
RATE_LIMIT_META_CODES = {130429, 80007}


class MetaAPIError(RuntimeError):
    """Base error for Meta WhatsApp Cloud API failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        error_code: int | None = None,
        error_subcode: int | None = None,
        permanent: bool = False,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.permanent = permanent
        self.details = details or {}


class MetaAuthError(MetaAPIError):
    """Raised when authentication (token or secret) fails."""


class MetaRateLimitError(MetaAPIError):
    """Raised when hitting Meta API throughput or quota limits."""


class MetaNetworkError(MetaAPIError):
    """Raised on connection timeouts or transport errors."""


@dataclass
class MetaMessage:
    id: str
    from_: str  # Normalized E.164 (+<country><number>)
    timestamp: str
    type: str  # "text", "audio", "image", etc.
    text: str | None = None
    media_id: str | None = None
    media_mime_type: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetaStatus:
    id: str  # wamid.<id>
    status: str  # "sent", "delivered", "read", "failed"
    timestamp: str
    recipient_id: str  # E.164 phone
    error_code: int | None = None
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetaEvent:
    object: str
    messages: list[MetaMessage] = field(default_factory=list)
    statuses: list[MetaStatus] = field(default_factory=list)
    unsupported: list[dict[str, Any]] = field(default_factory=list)


def validate_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 header using HMAC-SHA256 in constant time."""
    if not signature_header or not app_secret or not isinstance(raw_body, (bytes, bytearray)):
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), bytes(raw_body), hashlib.sha256).hexdigest()
    actual = signature_header[len("sha256=") :].strip()
    return hmac.compare_digest(expected, actual)


def verify_challenge(
    mode: str | None, token: str | None, challenge: str | None, expected_token: str
) -> str | None:
    """Handle the GET webhook verification handshake from Meta. Returns challenge if valid."""
    if not mode or not token or not challenge or not expected_token:
        return None
    if mode == "subscribe" and hmac.compare_digest(token, expected_token):
        return challenge
    return None


def normalize_meta_phone(raw: str | None) -> str:
    """Meta provides numbers like '14155552671' without leading '+'. Returns '+14155552671'."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw.strip())
    return ("+" + digits) if digits else ""


def parse_webhook_payload(payload: dict[str, Any]) -> MetaEvent:
    """Safely extract normalized messages, delivery statuses and unsupported events from a Meta payload."""
    if not isinstance(payload, dict):
        return MetaEvent(object="unknown")

    obj_name = str(payload.get("object", "whatsapp_business_account"))
    event = MetaEvent(object=obj_name)

    entries = payload.get("entry")
    if not isinstance(entries, list):
        return event

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue

        for change in changes:
            if not isinstance(change, dict):
                continue
            field_name = change.get("field")
            value = change.get("value")
            if field_name != "messages" or not isinstance(value, dict):
                event.unsupported.append(change)
                continue

            # Inbound messages
            raw_messages = value.get("messages")
            if isinstance(raw_messages, list):
                for m in raw_messages:
                    if not isinstance(m, dict):
                        continue
                    m_id = str(m.get("id") or "")
                    from_num = normalize_meta_phone(m.get("from"))
                    m_type = str(m.get("type") or "unknown")
                    ts = str(m.get("timestamp") or "")

                    text_body = None
                    if m_type == "text":
                        text_obj = m.get("text")
                        if isinstance(text_obj, dict):
                            text_body = str(text_obj.get("body") or "")

                    media_id = None
                    media_mime = None
                    if m_type in ("audio", "voice", "document", "image", "video"):
                        media_obj = m.get(m_type)
                        if isinstance(media_obj, dict):
                            media_id = str(media_obj.get("id") or "") or None
                            media_mime = str(media_obj.get("mime_type") or "") or None

                    event.messages.append(
                        MetaMessage(
                            id=m_id,
                            from_=from_num,
                            timestamp=ts,
                            type=m_type,
                            text=text_body,
                            media_id=media_id,
                            media_mime_type=media_mime,
                            raw=m,
                        )
                    )

            # Delivery statuses
            raw_statuses = value.get("statuses")
            if isinstance(raw_statuses, list):
                for s in raw_statuses:
                    if not isinstance(s, dict):
                        continue
                    s_id = str(s.get("id") or "")
                    s_status = str(s.get("status") or "")
                    ts = str(s.get("timestamp") or "")
                    recip = normalize_meta_phone(s.get("recipient_id"))

                    err_code = None
                    err_msg = None
                    errors = s.get("errors")
                    if isinstance(errors, list) and errors:
                        err0 = errors[0]
                        if isinstance(err0, dict):
                            err_code = err0.get("code")
                            err_msg = err0.get("title") or err0.get("message")

                    event.statuses.append(
                        MetaStatus(
                            id=s_id,
                            status=s_status,
                            timestamp=ts,
                            recipient_id=recip,
                            error_code=err_code,
                            error_message=err_msg,
                            raw=s,
                        )
                    )

    return event


def meta_media_url_ok(url: str, allow_http: bool = False) -> bool:
    """Validate that the media download URL originates from a trusted Meta domain."""
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
    except ValueError:
        return False
    if allow_http:
        if parts.scheme not in ("https", "http"):
            return False
    elif parts.scheme != "https":
        return False
    host = (parts.hostname or "").lower()
    return (
        host.endswith(".facebook.com")
        or host.endswith(".fbcdn.net")
        or host.endswith(".whatsapp.net")
        or host == "lookaside.fbsbx.com"
        or host.endswith(".fbsbx.com")
        or (allow_http and host in ("localhost", "127.0.0.1", "testserver"))
    )


class MetaWhatsAppClient:
    """Client for Meta WhatsApp Cloud API (Graph API v21+)."""

    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        *,
        api_version: str = DEFAULT_GRAPH_VERSION,
        base_url: str = GRAPH_API_BASE,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ):
        self.access_token = access_token.strip()
        self.phone_number_id = phone_number_id.strip()
        self.api_version = api_version.strip() or DEFAULT_GRAPH_VERSION
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._custom_client = http_client

    def _client(self) -> httpx.Client:
        if self._custom_client is not None:
            return self._custom_client
        return httpx.Client(timeout=self.timeout)

    def _headers(self) -> dict[str, str]:
        if not self.access_token:
            raise MetaAuthError("Meta access token is not configured", status_code=401, permanent=True)
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _handle_error_response(self, response: httpx.Response) -> None:
        status = response.status_code
        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError):
            body = {}

        err_obj = body.get("error", {}) if isinstance(body, dict) else {}
        msg = err_obj.get("message") or f"Meta Graph API error (HTTP {status})"
        code = err_obj.get("code")
        subcode = err_obj.get("error_subcode")
        details = err_obj

        permanent = (code in PERMANENT_META_CODES) or (400 <= status < 500 and status != 429)

        if status == 401 or code == 190:
            raise MetaAuthError(msg, status_code=status, error_code=code, error_subcode=subcode, permanent=True, details=details)
        if status == 429 or code in RATE_LIMIT_META_CODES:
            raise MetaRateLimitError(msg, status_code=status, error_code=code, error_subcode=subcode, permanent=False, details=details)

        raise MetaAPIError(msg, status_code=status, error_code=code, error_subcode=subcode, permanent=permanent, details=details)

    def send_text(self, to: str, body: str, *, preview_url: bool = False) -> dict[str, Any]:
        """Send a standard free-form text message within the 24-hour service window."""
        if not self.phone_number_id:
            raise MetaAPIError("Meta phone_number_id is not configured", status_code=400, permanent=True)

        clean_to = to.removeprefix("whatsapp:").lstrip("+").strip()
        if not clean_to or not clean_to.isdigit():
            raise MetaAPIError(f"Invalid recipient phone number: {to!r}", status_code=400, permanent=True)

        url = f"{self.base_url}/{self.api_version}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_to,
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": body,
            },
        }

        client = self._client()
        try:
            resp = client.post(url, json=payload, headers=self._headers())
            if not resp.is_success:
                self._handle_error_response(resp)
            return resp.json()
        except httpx.TimeoutException as e:
            raise MetaNetworkError(f"Meta API timeout: {e}") from e
        except httpx.RequestError as e:
            raise MetaNetworkError(f"Meta API network error: {e}") from e
        finally:
            if self._custom_client is None:
                client.close()

    def get_media_url(self, media_id: str) -> dict[str, Any]:
        """Query Meta Graph API to resolve a media ID into a downloadable temporary URL."""
        if not media_id or not media_id.strip():
            raise MetaAPIError("Invalid media_id", status_code=400, permanent=True)

        url = f"{self.base_url}/{self.api_version}/{media_id.strip()}"
        client = self._client()
        try:
            resp = client.get(url, headers=self._headers())
            if not resp.is_success:
                self._handle_error_response(resp)
            return resp.json()
        except httpx.TimeoutException as e:
            raise MetaNetworkError(f"Meta media resolution timeout: {e}") from e
        except httpx.RequestError as e:
            raise MetaNetworkError(f"Meta media resolution error: {e}") from e
        finally:
            if self._custom_client is None:
                client.close()

    def download_media(self, media_url: str, max_bytes: int = MAX_MEDIA_BYTES) -> tuple[bytes, str]:
        """Download binary media from Meta lookaside URL using Bearer auth."""
        allow_http = self.base_url.startswith("http://")
        if not meta_media_url_ok(media_url, allow_http=allow_http):
            raise MetaAPIError(f"Untrusted or invalid media URL: {media_url!r}", status_code=400, permanent=True)

        client = self._client()
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            with client.stream("GET", media_url, headers=headers, follow_redirects=True) as resp:
                if not resp.is_success:
                    self._handle_error_response(resp)
                content_type = resp.headers.get("content-type", "application/octet-stream")
                chunks = bytearray()
                for chunk in resp.iter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > max_bytes:
                        raise MetaAPIError(f"Media exceeds maximum size of {max_bytes} bytes", permanent=True)
                return bytes(chunks), content_type
        except httpx.TimeoutException as e:
            raise MetaNetworkError(f"Meta media download timeout: {e}") from e
        except httpx.RequestError as e:
            raise MetaNetworkError(f"Meta media download error: {e}") from e
        finally:
            if self._custom_client is None:
                client.close()

    def fetch_media_by_id(self, media_id: str, max_bytes: int = MAX_MEDIA_BYTES) -> tuple[bytes, str]:
        """Resolve and download media in a single two-step authenticated call."""
        info = self.get_media_url(media_id)
        url = info.get("url")
        if not url:
            raise MetaAPIError("Meta did not return a valid download URL for media", permanent=True)
        return self.download_media(url, max_bytes=max_bytes)
