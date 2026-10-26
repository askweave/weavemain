"""Voice notes: transcribed locally, then handled exactly like a typed message."""

import pytest
from test_sms import OWNER, Env

from genesis.sms.voice import VoiceError, twilio_media_url_ok

SID = "AC" + "0" * 32
MEDIA = f"https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages/MM{'1' * 32}/Media/ME{'2' * 32}"


@pytest.fixture
def env(settings):
    e = Env(settings)
    e.heard = []
    e.transcript = "build me an app that tracks my water intake every day"

    def fetch(url):
        e.heard.append(url)
        return b"OggS fake audio"

    def transcribe(audio):
        if isinstance(e.transcript, Exception):
            raise e.transcript
        return e.transcript

    voice = e.sms.voice
    voice.fetch, voice.transcribe, voice.synchronous = fetch, transcribe, True
    return e


def voice_note(env, frm=OWNER, sid=None):
    return env.text(frm, "", sid=sid, extra={"NumMedia": "1", "MediaUrl0": MEDIA,
                                             "MediaContentType0": "audio/ogg; codecs=opus"})


def test_voice_note_starts_a_build_and_repeats_what_it_heard(env):
    r = voice_note(env)
    assert r.status_code == 200 and env.heard == [MEDIA]
    reply = env.last()
    assert reply.startswith('You said: "build me an app that tracks my water intake')
    assert "Build ID" in reply and len(env.jobs()) == 1


def test_voice_change_request(env):
    env.text(OWNER, "Build me a habit tracker with streaks")
    env.drain()
    env.transcript = "make the buttons bigger and use a green theme"
    voice_note(env)
    assert env.jobs()[-1]["kind"] == "change"


def test_unclear_audio_asks_to_type(env):
    env.transcript = VoiceError("I couldn't hear any words in that voice note")
    voice_note(env)
    assert "couldn't use that voice note" in env.last() and env.jobs() == []


def test_unknown_senders_are_not_transcribed(env):
    voice_note(env, frm="+15551234567")
    assert env.heard == []


def test_duplicate_delivery_is_transcribed_once(env):
    sid = "MM" + "3" * 32
    voice_note(env, sid=sid)
    voice_note(env, sid=sid)
    assert len(env.heard) == 1 and len(env.jobs()) == 1


def test_images_are_not_voice(env):
    env.text(OWNER, "", extra={"NumMedia": "1", "MediaUrl0": MEDIA, "MediaContentType0": "image/jpeg"})
    assert env.heard == [] and "voice note" in env.last()


def test_media_urls_are_only_fetched_from_our_twilio_account():
    assert twilio_media_url_ok(MEDIA, SID)
    assert not twilio_media_url_ok(MEDIA.replace("api.twilio.com", "evil.example"), SID)
    assert not twilio_media_url_ok(MEDIA.replace(SID, "AC" + "9" * 32), SID)
    assert not twilio_media_url_ok(MEDIA.replace("https", "http"), SID)
