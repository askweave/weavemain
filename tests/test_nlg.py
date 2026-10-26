"""Tests for Natural Language Generation (NLG) and user-facing branding.

Verifies:
1. NlgPresenter rephrasing of deterministic facts.
2. Immediate deterministic fallback on error, timeout, or disabled setting.
3. Strict factual integrity: URLs, download links, build refs must not be lost.
4. Stripping of accidental "Weave: " / "Genesis: " prefixes.
5. End-to-end guarantee that outbound messages do not have product name prefixes.
"""

import time
import pytest
from conftest import FakeBuilder, FakeGemini, manifest
from pydantic import BaseModel

from genesis.config import Settings
from genesis.sms.nlg import NlgOutput, NlgPresenter
from genesis.sms.service import Inbound, SmsService
from genesis.sms.store import SmsStore
from test_sms import Env, OWNER, FakeProvider


class FakeAiForNlg:
    def __init__(self, reply: str = "Here is your app!", delay: float = 0.0, fail: bool = False):
        self.reply = reply
        self.delay = delay
        self.fail = fail
        self.configured = True
        self.calls = []

    def _structured(self, system: str, user: str, schema: type[BaseModel], attempts: int = 1,
                    model: str | None = None, timeout: int | None = None):
        self.calls.append((system, user, schema, model, timeout))
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("Gemini error simulation")
        return NlgOutput(message=self.reply), {"model": model}


def test_nlg_presenter_success(settings: Settings):
    settings.nlg_enabled = True
    ai = FakeAiForNlg(reply="Awesome! I've started building your app now.")
    presenter = NlgPresenter(settings, ai)

    result = presenter.present(
        kind="build_accepted",
        facts={"action": "build_accepted", "ref": "G-12345"},
        fallback="Got it! Build ID: G-12345. Ask anytime.",
        user_query="Make a habit tracker",
    )
    # The fake returned our reply (wait, does it have G-12345? If ref is in critical_keys, candidate must contain it)
    # So let's provide reply with G-12345
    ai.reply = "Awesome! I've started building your app now. (Ref: G-12345)"
    result = presenter.present(
        kind="build_accepted",
        facts={"action": "build_accepted", "ref": "G-12345"},
        fallback="Got it! Build ID: G-12345. Ask anytime.",
        user_query="Make a habit tracker",
    )
    assert result == "Awesome! I've started building your app now. (Ref: G-12345)"
    assert len(ai.calls) == 2


def test_nlg_disabled(settings: Settings):
    settings.nlg_enabled = False
    ai = FakeAiForNlg(reply="This should not be used.")
    presenter = NlgPresenter(settings, ai)

    fallback = "Deterministic fallback text."
    result = presenter.present("greeting", {}, fallback)
    assert result == fallback
    assert len(ai.calls) == 0


def test_nlg_timeout_fallback(settings: Settings):
    settings.nlg_enabled = True
    settings.nlg_timeout = 0.1
    ai = FakeAiForNlg(reply="Delayed reply", delay=0.5)
    presenter = NlgPresenter(settings, ai)

    fallback = "Fallback due to timeout."
    result = presenter.present("greeting", {}, fallback)
    assert result == fallback


def test_nlg_error_fallback(settings: Settings):
    settings.nlg_enabled = True
    ai = FakeAiForNlg(fail=True)
    presenter = NlgPresenter(settings, ai)

    fallback = "Fallback due to exception."
    result = presenter.present("greeting", {}, fallback)
    assert result == fallback


def test_nlg_critical_fact_omission_triggers_fallback(settings: Settings):
    settings.nlg_enabled = True
    # The AI forgot to include the download URL in the candidate text!
    ai = FakeAiForNlg(reply="Your app is ready, go check it out!")
    presenter = NlgPresenter(settings, ai)

    fallback = "Your app is ready! Download: https://example.com/download/token123"
    result = presenter.present(
        kind="download",
        facts={"action": "download", "download_url": "https://example.com/download/token123"},
        fallback=fallback,
    )
    # Must fallback because https://example.com/download/token123 was missing in candidate!
    assert result == fallback


def test_nlg_critical_fact_preservation_succeeds(settings: Settings):
    settings.nlg_enabled = True
    url = "https://example.com/download/token123"
    ai = FakeAiForNlg(reply=f"Here is your download link: {url} Have fun!")
    presenter = NlgPresenter(settings, ai)

    fallback = f"Your app is ready: {url}"
    result = presenter.present(
        kind="download",
        facts={"action": "download", "download_url": url},
        fallback=fallback,
    )
    assert result == f"Here is your download link: {url} Have fun!"


def test_nlg_strips_accidental_prefixes(settings: Settings):
    settings.nlg_enabled = True
    ai = FakeAiForNlg(reply="Weave: Hello there! What can I build for you today?")
    presenter = NlgPresenter(settings, ai)

    result = presenter.present("greeting", {}, "Fallback")
    assert result == "Hello there! What can I build for you today?"
    assert not result.startswith("Weave:")

    ai.reply = "Genesis: How can I help?"
    result = presenter.present("greeting", {}, "Fallback")
    assert result == "How can I help?"
    assert not result.startswith("Genesis:")


def test_outbound_messages_have_no_genesis_or_weave_prefix(settings: Settings):
    """End-to-end verification that outbound messages are never prefixed with Genesis: or Weave:."""
    env = Env(settings)
    # Send a HELP message
    env.text(OWNER, "HELP")
    body = env.last()
    assert body is not None
    assert not body.startswith("Genesis:")
    assert not body.startswith("Weave:")

    # Send a greeting
    env.text(OWNER, "Hi")
    body = env.last()
    assert body is not None
    assert not body.startswith("Genesis:")
    assert not body.startswith("Weave:")
