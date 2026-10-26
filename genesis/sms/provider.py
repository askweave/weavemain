"""SMS providers. The Genesis engine only talks to SmsProvider, so another gateway (e.g. an Indian DLT-registered
provider) can be added as one class without touching the queue, commands or build pipeline."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from ..config import Settings
from .phone import mask

log = logging.getLogger("genesis.sms.provider")

# Twilio error codes that will fail the same way on every retry.
# https://www.twilio.com/docs/api/errors
PERMANENT_TWILIO_CODES = {
    21211,  # invalid 'To' number
    21408,  # permission to send to this region not enabled (Messaging Geo Permissions)
    21606,  # 'From' number is not a valid, SMS-capable number for this account
    21608,  # trial account: 'To' number is not verified
    21610,  # recipient replied STOP
    21612,  # cannot route between these numbers
    21614,  # 'To' is not a mobile number
    21659,  # 'From' is not a Twilio number
    21703,  # Messaging Service has no phone numbers
    30007,  # filtered by carrier
}


@dataclass
class SendResult:
    sid: str
    status: str


class SendError(RuntimeError):
    def __init__(self, message: str, *, permanent: bool, code: int | None = None):
        super().__init__(message)
        self.permanent = permanent
        self.code = code


class SmsProvider(Protocol):
    name: str

    def send(self, to: str, body: str, status_callback: str | None, sender: str | None = None) -> SendResult: ...

    def validate_request(self, url: str, params: Mapping[str, str], signature: str) -> bool: ...


class TwilioProvider:
    name = "twilio"

    def __init__(self, settings: Settings):
        self.s = settings
        self._client = None
        from twilio.request_validator import RequestValidator

        self._validator = RequestValidator(settings.twilio_auth_token) if settings.twilio_auth_token else None

    def _get_client(self):
        if self._client is None:
            from twilio.rest import Client

            self._client = Client(self.s.twilio_account_sid, self.s.twilio_auth_token,
                                  region=self.s.twilio_region or None, edge=self.s.twilio_edge or None)
        return self._client

    def send(self, to: str, body: str, status_callback: str | None, sender: str | None = None) -> SendResult:
        """`sender` is the number the user wrote to. WhatsApp only allows free-form replies from that number
        (any other sender needs an approved template: error 21654), so it wins over the configured default."""
        from twilio.base.exceptions import TwilioException, TwilioRestException

        if not (self.s.twilio_account_sid and self.s.twilio_auth_token):
            raise SendError("Twilio credentials are not configured", permanent=True)
        # The address decides the channel: 'whatsapp:+91...' goes to WhatsApp, '+91...' to SMS.
        whatsapp = to.startswith("whatsapp:")
        kwargs: dict = {"to": to, "body": body}
        if self.s.twilio_messaging_service_sid:
            kwargs["messaging_service_sid"] = self.s.twilio_messaging_service_sid
        elif whatsapp:
            frm = sender or self.s.whatsapp_sender
            if not frm:
                raise SendError("no WhatsApp sender configured (TWILIO_WHATSAPP_NUMBER)", permanent=True)
            kwargs["from_"] = "whatsapp:" + frm
        else:
            frm = sender or self.s.sms_sender
            if not frm:
                raise SendError("no SMS sender configured (TWILIO_PHONE_NUMBER)", permanent=True)
            kwargs["from_"] = frm
        if whatsapp and self.s.twilio_whatsapp_content_sid:
            # Template whose body is exactly {{1}}: same text, accepted by senders that require ContentSid.
            del kwargs["body"]
            kwargs["content_sid"] = self.s.twilio_whatsapp_content_sid
            kwargs["content_variables"] = json.dumps({"1": body})
        if status_callback:
            kwargs["status_callback"] = status_callback
        try:
            msg = self._get_client().messages.create(**kwargs)
        except TwilioRestException as e:
            permanent = e.code in PERMANENT_TWILIO_CODES or (e.status is not None and 400 <= e.status < 500 and e.status != 429)
            raise SendError(f"Twilio {e.status} error {e.code}: {e.msg}", permanent=permanent, code=e.code) from None
        except TwilioException as e:
            raise SendError(f"Twilio error: {type(e).__name__}", permanent=False) from None
        except OSError as e:  # network
            raise SendError(f"network error: {type(e).__name__}", permanent=False) from None
        return SendResult(sid=msg.sid, status=str(msg.status or "queued"))

    def validate_request(self, url: str, params: Mapping[str, str], signature: str) -> bool:
        if self._validator is None or not signature:
            return False
        return bool(self._validator.validate(url, dict(params), signature))


class LogProvider:
    """Development provider: writes outbound SMS to data/sms-outbox.log instead of sending them.
    Inbound webhooks still require a valid Twilio signature (when an auth token is configured)."""

    name = "log"

    def __init__(self, settings: Settings):
        self.path: Path = settings.data_dir / "sms-outbox.log"
        self._twilio = TwilioProvider(settings)
        self.sent: list[tuple[str, str]] = []

    def send(self, to: str, body: str, status_callback: str | None, sender: str | None = None) -> SendResult:
        self.sent.append((to, body))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] to {mask(to)}:\n{body}\n\n")
        return SendResult(sid=f"LOG{int(time.time() * 1000)}{len(self.sent)}", status="sent")

    def validate_request(self, url: str, params: Mapping[str, str], signature: str) -> bool:
        return self._twilio.validate_request(url, params, signature)


class MetaWhatsAppProvider:
    """Meta WhatsApp Cloud API (Graph API) messaging provider."""

    name = "meta"

    def __init__(self, settings: Settings, client=None):
        self.s = settings
        self._client = client

    def _get_client(self):
        if self._client is None:
            from .meta import MetaWhatsAppClient

            self._client = MetaWhatsAppClient(
                access_token=self.s.meta_access_token,
                phone_number_id=self.s.meta_phone_number_id,
                api_version=self.s.meta_graph_api_version,
            )
        return self._client

    def send(self, to: str, body: str, status_callback: str | None = None, sender: str | None = None) -> SendResult:
        if not (self.s.meta_access_token and self.s.meta_phone_number_id):
            raise SendError("Meta WhatsApp credentials are not configured (META_ACCESS_TOKEN, META_PHONE_NUMBER_ID)", permanent=True)

        from .meta import (
            MetaAPIError,
            MetaAuthError,
            MetaNetworkError,
            MetaRateLimitError,
        )

        client = self._get_client()
        try:
            resp = client.send_text(to=to, body=body)
            messages = resp.get("messages") or []
            sid = messages[0].get("id") if messages and isinstance(messages[0], dict) else f"meta_{int(time.time() * 1000)}"
            return SendResult(sid=sid, status="sent")
        except MetaRateLimitError as e:
            code_str = f" [{e.error_code}]" if e.error_code else ""
            raise SendError(f"Meta rate limit{code_str}: {e}", permanent=False, code=e.error_code) from None
        except MetaAuthError as e:
            code_str = f" [{e.error_code}]" if e.error_code else ""
            raise SendError(f"Meta auth error{code_str}: {e}", permanent=True, code=e.error_code) from None
        except MetaNetworkError as e:
            raise SendError(f"Meta network error: {e}", permanent=False) from None
        except MetaAPIError as e:
            code_str = f" [{e.error_code}]" if e.error_code else ""
            raise SendError(f"Meta API error{code_str}: {e}", permanent=e.permanent, code=e.error_code) from None
        except Exception as e:
            raise SendError(f"Meta unexpected error: {type(e).__name__}: {e}", permanent=False) from None

    def validate_request(self, url: str, params: Mapping[str, str], signature: str) -> bool:
        return False


class OffProvider:
    """Disabled messaging provider."""

    name = "off"

    def send(self, to: str, body: str, status_callback: str | None = None, sender: str | None = None) -> SendResult:
        raise SendError("Messaging provider is disabled", permanent=True)

    def validate_request(self, url: str, params: Mapping[str, str], signature: str) -> bool:
        return False


class ChannelRouter:
    """Sends 'web:' addresses to the Genesis web chat (stored in SQLite, nothing leaves the machine);
    routes 'whatsapp:' to Meta or Twilio depending on GENESIS_WHATSAPP_PROVIDER;
    all other addresses to the external SMS provider (Twilio, Log, or Off)."""

    def __init__(self, external: SmsProvider, settings: Settings | None = None, meta: SmsProvider | None = None):
        self.external = external
        self.settings = settings
        self._meta = meta
        self.name = external.name

    def _get_meta(self) -> SmsProvider:
        if self._meta is None:
            s = self.settings or Settings()
            self._meta = MetaWhatsAppProvider(s)
        return self._meta

    def send(self, to: str, body: str, status_callback: str | None, sender: str | None = None) -> SendResult:
        if to.startswith("web:"):
            return SendResult(sid=f"WEB{time.time_ns()}", status="delivered")

        if to.startswith("whatsapp:"):
            wp = self.settings.whatsapp_provider if self.settings else "twilio"
            if wp == "meta":
                return self._get_meta().send(to, body, status_callback, sender)
            elif wp == "off":
                raise SendError("WhatsApp sending is disabled (GENESIS_WHATSAPP_PROVIDER=off)", permanent=True)
            elif wp == "twilio":
                return self.external.send(to, body, status_callback, sender)
            else:
                raise SendError(f"Unsupported WhatsApp provider: {wp}", permanent=True)

        if self.settings and self.settings.sms_provider == "off":
            raise SendError("SMS sending is disabled (GENESIS_SMS_PROVIDER=off)", permanent=True)
        return self.external.send(to, body, status_callback, sender)

    def validate_request(self, url: str, params: Mapping[str, str], signature: str) -> bool:
        return self.external.validate_request(url, params, signature)


def make_provider(settings: Settings) -> SmsProvider:
    if settings.sms_provider == "log":
        return LogProvider(settings)
    if settings.sms_provider == "off":
        return OffProvider()
    return TwilioProvider(settings)
