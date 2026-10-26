"""Voice notes: download the audio Twilio received and transcribe it on this computer with Whisper.

Transcription is local (faster-whisper on the CPU): no API, no cost, and the audio never leaves the Mac
except for the download from Twilio. The model is downloaded once on first use (~150 MB for "base").
Twilio media is fetched with the account credentials, so only api.twilio.com URLs are ever requested.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit

from ..config import Settings

log = logging.getLogger("genesis.sms")

MAX_AUDIO_BYTES = 16 * 1024 * 1024  # WhatsApp's own limit for audio
MAX_SECONDS = 300
AUDIO_TYPES = ("audio/",)


class VoiceError(RuntimeError):
    """Safe to show to the user."""


def is_audio(content_type: str) -> bool:
    return (content_type or "").lower().startswith(AUDIO_TYPES)


def twilio_media_url_ok(url: str, account_sid: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (parts.scheme == "https" and parts.hostname == "api.twilio.com" and not parts.port
            and parts.path.startswith(f"/2010-04-01/Accounts/{account_sid}/Messages/"))


def fetch_twilio_media(url: str, settings: Settings) -> bytes:
    import httpx

    if not twilio_media_url_ok(url, settings.twilio_account_sid):
        raise VoiceError("Unexpected media location")
    auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    # httpx drops the Authorization header when a redirect leaves api.twilio.com (media is served from a CDN).
    with httpx.Client(timeout=30, follow_redirects=True, max_redirects=5) as client:
        with client.stream("GET", url, auth=auth) as r:
            if r.status_code != 200:
                raise VoiceError(f"Couldn't download the voice note (HTTP {r.status_code})")
            data = bytearray()
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > MAX_AUDIO_BYTES:
                    raise VoiceError("That voice note is too long")
    return bytes(data)


class Transcriber:
    def __init__(self, settings: Settings):
        self.s = settings
        self._model = None
        self._lock = threading.Lock()

    def _get_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise VoiceError("Voice notes need faster-whisper: pip install faster-whisper") from e
            log.info("Loading Whisper model %s (first use downloads it)", self.s.voice_model)
            self._model = WhisperModel(self.s.voice_model, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, audio: bytes) -> str:
        with self._lock, tempfile.TemporaryDirectory(prefix="genesis-voice-") as tmp:
            path = Path(tmp) / "note.audio"
            path.write_bytes(audio)
            model = self._get_model()
            segments, info = model.transcribe(str(path), beam_size=5, vad_filter=True,
                                              language=self.s.voice_language or None)
            if info.duration and info.duration > MAX_SECONDS:
                raise VoiceError(f"Please keep voice notes under {MAX_SECONDS // 60} minutes")
            text = " ".join(seg.text.strip() for seg in segments).strip()
        if not text:
            raise VoiceError("I couldn't hear any words in that voice note")
        return text


def fetch_meta_media(media_id: str, client, max_bytes: int = MAX_AUDIO_BYTES) -> tuple[bytes, str]:
    """Resolve and download audio for a Meta WhatsApp voice note."""
    from .meta import MetaAPIError, MetaAuthError, MetaNetworkError, MetaRateLimitError

    try:
        info = client.get_media_url(media_id)
    except MetaAuthError as e:
        raise VoiceError("WhatsApp authorization error") from e
    except MetaRateLimitError as e:
        raise VoiceError("WhatsApp rate limit exceeded") from e
    except (MetaAPIError, MetaNetworkError) as e:
        raise VoiceError(f"Could not retrieve media details ({e})") from e

    url = info.get("url") if isinstance(info, dict) else None
    if not url:
        raise VoiceError("Voice note download link is expired or unavailable")

    mime = (info.get("mime_type") or "").lower()
    if mime and not is_audio(mime):
        raise VoiceError("I can only read text and audio voice notes")

    file_size = info.get("file_size")
    if file_size and int(file_size) > max_bytes:
        raise VoiceError("That voice note is too long")

    try:
        data, content_type = client.download_media(url, max_bytes=max_bytes)
    except MetaAuthError as e:
        raise VoiceError("WhatsApp authorization error") from e
    except MetaRateLimitError as e:
        raise VoiceError("WhatsApp rate limit exceeded") from e
    except (MetaAPIError, MetaNetworkError) as e:
        raise VoiceError(f"Could not download audio ({e})") from e

    if content_type and not is_audio(content_type):
        raise VoiceError("I can only read text and audio voice notes")
    if not data:
        raise VoiceError("Voice note was empty")

    return data, content_type or mime


class VoiceInbox:
    """Turns an inbound voice note into text off the webhook thread."""

    def __init__(self, settings: Settings, *, fetch=None, fetch_meta=None, transcribe=None, synchronous: bool = False):
        self.s = settings
        self.fetch = fetch or (lambda url: fetch_twilio_media(url, settings))
        self.fetch_meta = fetch_meta or (lambda media_id, client: fetch_meta_media(media_id, client))
        self._transcriber = Transcriber(settings)
        self.transcribe = transcribe or self._transcriber.transcribe
        self.synchronous = synchronous
        self._pool = None

    def submit(self, fn) -> None:
        if self.synchronous:
            fn()
            return
        if self._pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="genesis-voice")
        self._pool.submit(fn)

    def to_text(self, media_url: str) -> str:
        return self.transcribe(self.fetch(media_url))
