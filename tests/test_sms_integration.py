"""Opt-in integration tests: the SMS flow through the REAL Gradle build (and optionally real Gemini).

    GENESIS_RUN_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_sms_integration.py   # real Gradle, fake AI
    GENESIS_RUN_INTEGRATION=1 GENESIS_RUN_GEMINI=1 ...                                      # real Gradle + Gemini (uses quota)

No SMS is ever sent: outbound messages go to a fake provider."""

import os
import zipfile

import pytest
from conftest import FakeGemini, manifest
from test_sms import OWNER, Env, link_from

from genesis.config import Settings
from genesis.core.builder import AndroidBuilder

pytestmark = pytest.mark.skipif(os.environ.get("GENESIS_RUN_INTEGRATION") != "1",
                                reason="set GENESIS_RUN_INTEGRATION=1 to run real Gradle builds")


@pytest.fixture
def real_settings(settings, tmp_path):
    real = Settings()
    if not real.doctor()["ready"]:
        pytest.skip("Android toolchain not ready (python -m genesis doctor)")
    settings.java_home, settings.android_home = real.java_home, real.android_home
    settings.build_timeout = 1500
    return settings


class SharedCacheBuilder(AndroidBuilder):
    """Real builder, but reuses the machine's Gradle cache so the test doesn't re-download dependencies."""

    def gradle_env(self):
        env = super().gradle_env()
        env["GRADLE_USER_HOME"] = str(Settings().gradle_user_home)
        return env


def test_sms_flow_with_real_gradle_build(real_settings):
    gemini = None
    if os.environ.get("GENESIS_RUN_GEMINI") == "1":
        from genesis.core.gemini import GeminiClient

        real_settings.gemini_api_key = Settings().gemini_api_key
        gemini = GeminiClient(real_settings)
    env = Env(real_settings, gemini=gemini or FakeGemini(manifest()), builder=SharedCacheBuilder(real_settings))
    env.text(OWNER, "Build me a simple habit tracker with daily streaks")
    env.drain()
    job = env.jobs()[0]
    assert job["status"] == "succeeded", env.orch.store.get(job["build_id"]).get("error")
    final = env.last()
    path = link_from(final).removeprefix(real_settings.public_base_url)
    r = env.client.get(path)
    assert r.status_code == 200 and len(r.content) > 100_000
    apk = real_settings.data_dir / "downloaded.apk"
    apk.write_bytes(r.content)
    with zipfile.ZipFile(apk) as z:
        assert "classes.dex" in z.namelist()

    env.text(OWNER, "Make the theme dark")
    env.drain()
    change = env.jobs()[1]
    assert change["status"] == "succeeded", env.orch.store.get(change["build_id"]).get("error")
    assert env.orch.store.get(change["build_id"])["package_id"] == env.orch.store.get(job["build_id"])["package_id"]
