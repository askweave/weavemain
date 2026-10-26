from pathlib import Path

from conftest import BROKEN, GOOD, FakeBuilder, FakeGemini, manifest

from genesis.core.builder import AndroidBuilder, android_string_escape
from genesis.core.gemini import GeminiError
from genesis.core.jobs import Orchestrator
from genesis.core.schemas import BuildRequest

REQ = BuildRequest(prompt="A workout tracker for lifting sessions")


def run(settings, gemini):
    builder = FakeBuilder(settings)
    orch = Orchestrator(settings, gemini, builder=builder)
    job = orch.run_sync(REQ)
    return orch, builder, job


def test_success_first_try(settings):
    orch, builder, job = run(settings, FakeGemini(manifest()))
    assert job["status"] == "succeeded"
    assert builder.runs == 1
    apk = orch.store.path(job["id"]) / "artifact" / job["apk"]["filename"]
    assert apk.is_file() and job["apk"]["filename"].startswith("lift-log-")
    ws = orch.store.path(job["id"]) / "workspace"
    # Protected template files present and server-written values applied.
    assert (ws / "app/src/main/java/com/genesis/app/MainActivity.kt").is_file()
    assert "applicationId=com.genesis.liftlog" in (ws / "genesis.properties").read_text()
    assert "0xFF7C4DFF" in (ws / "app/src/main/java/com/genesis/app/ui/theme/ThemeConfig.kt").read_text()
    assert "Lift Log" in (ws / "app/src/main/res/values/strings.xml").read_text()
    # Bulky intermediates cleaned up, sources kept.
    assert not (ws / "app/build").exists()
    assert (ws / "app/src/main/java/com/genesis/app/GenesisApp.kt").read_text() == GOOD


def test_repair_then_success(settings):
    gem = FakeGemini(manifest(BROKEN), repairs=[GOOD])
    _, builder, job = run(settings, gem)
    assert job["status"] == "succeeded"
    assert builder.runs == 2 and gem.repair_calls == 1
    assert job["attempts"][0]["errors"] == ["error: GenesisApp.kt:8:5 Unresolved reference 'Txt'."]
    assert job["attempts"][0]["patch"]["files"] == ["GenesisApp.kt"]


def test_repair_is_bounded(settings):
    gem = FakeGemini(manifest(BROKEN), repairs=[BROKEN, BROKEN, BROKEN, BROKEN])
    _, builder, job = run(settings, gem)
    assert job["status"] == "failed"
    assert builder.runs == 3  # initial + 2 repairs
    assert gem.repair_calls == 2
    assert "after 2 repair attempt" in job["error"]
    assert job["apk"] is None


def test_toolchain_failure_not_sent_to_ai(settings):
    gem = FakeGemini(manifest(GOOD.replace('"ok"', '"TOOLCHAIN_BOOM"')))
    _, builder, job = run(settings, gem)
    assert job["status"] == "failed" and gem.repair_calls == 0
    assert "outside generated code" in job["error"]


def test_gemini_error_reported(settings):
    _, builder, job = run(settings, FakeGemini(GeminiError("quota exhausted")))
    assert job["status"] == "failed" and "quota exhausted" in job["error"]
    assert builder.runs == 0


def test_unsafe_generation_rejected_without_build(settings):
    evil = GOOD.replace('Text("ok")', 'Runtime.getRuntime().exec("rm -rf /")')
    _, builder, job = run(settings, FakeGemini(manifest(evil)))
    assert job["status"] == "failed" and builder.runs == 0
    assert "validation" in job["error"]


def test_builds_are_isolated(settings):
    orch, _, j1 = run(settings, FakeGemini(manifest()))
    j2 = orch.run_sync(REQ)
    assert j1["id"] != j2["id"]
    assert orch.store.path(j1["id"]) != orch.store.path(j2["id"])
    assert len(orch.store.list()) == 2


def test_user_app_name_wins(settings):
    orch = Orchestrator(settings, FakeGemini(manifest()), builder=FakeBuilder(settings))
    job = orch.run_sync(BuildRequest(prompt="A workout tracker for lifting", app_name="Iron & Co"))
    assert job["app_name"] == "Iron & Co"
    ws = orch.store.path(job["id"]) / "workspace"
    assert "Iron &amp; Co" in (ws / "app/src/main/res/values/strings.xml").read_text()


def test_interrupted_jobs_marked_failed(settings):
    orch = Orchestrator(settings, FakeGemini(manifest()), builder=FakeBuilder(settings))
    job = orch.store.create(REQ)
    job["status"] = "running"
    orch.store.save(job)
    Orchestrator(settings, FakeGemini(manifest()), builder=FakeBuilder(settings))
    assert orch.store.get(job["id"])["status"] == "failed"


def test_gradle_env_excludes_secrets(settings, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret")
    env = AndroidBuilder(settings).gradle_env()
    assert "GEMINI_API_KEY" not in env
    assert "super-secret" not in "".join(env.values())


def test_string_escape():
    assert android_string_escape("Bob's <App> & \"Co\"") == "Bob\\'s &lt;App&gt; &amp; \\\"Co\\\""
    assert android_string_escape("@home") == "\\@home"


def test_only_assemble_debug_allowed(settings, tmp_path: Path):
    import pytest
    from genesis.core.builder import BuildError

    with pytest.raises(BuildError):
        AndroidBuilder(settings).run_gradle(tmp_path, tmp_path / "log", task="publish")


def test_change_build_edits_base_sources_and_keeps_package(settings):
    gem = FakeGemini(manifest())
    orch = Orchestrator(settings, gem, builder=FakeBuilder(settings))
    base = orch.run_sync(REQ)
    job = orch.create_job(BuildRequest(prompt="A workout tracker with a dark theme"), base_job_id=base["id"],
                          change_request="use a dark theme", source="sms")
    done = orch.run_existing(job["id"])
    assert done["status"] == "succeeded" and done["base_job_id"] == base["id"] and done["source"] == "sms"
    change, files, base_manifest = gem.modify_calls[0]
    assert change == "use a dark theme" and files["GenesisApp.kt"] == GOOD
    assert done["package_id"] == base_manifest.package_id == "com.genesis.liftlog"
    assert done["ai_calls"][0]["kind"] == "modify"
    theme = (orch.store.path(done["id"]) / "workspace/app/src/main/java/com/genesis/app/ui/theme/ThemeConfig.kt").read_text()
    assert 'GENESIS_THEME_MODE: String = "dark"' in theme


def test_change_build_requires_successful_base(settings):
    import pytest

    orch = Orchestrator(settings, FakeGemini(GeminiError("down")), builder=FakeBuilder(settings))
    failed = orch.run_sync(REQ)
    with pytest.raises(ValueError):
        orch.create_job(REQ, base_job_id=failed["id"])


def test_cancel_before_start(settings):
    events = []
    orch = Orchestrator(settings, FakeGemini(manifest()), builder=FakeBuilder(settings))
    job = orch.create_job(REQ)
    orch._cancel[job["id"]] = __import__("threading").Event()
    assert orch.cancel(job["id"])
    done = orch.run_existing(job["id"], listener=lambda j, ev: events.append(ev))
    assert done["status"] == "failed" and done["cancelled"] and done["message"] == "Build cancelled"
    assert events == ["failed"]


def test_listener_sees_real_stages_and_errors_are_contained(settings):
    events = []

    def listener(job, ev):
        events.append(ev)
        raise RuntimeError("listener bug")

    orch = Orchestrator(settings, FakeGemini(manifest()), builder=FakeBuilder(settings))
    done = orch.run_existing(orch.create_job(REQ)["id"], listener=listener)
    assert done["status"] == "succeeded"
    assert events == ["generating", "validating", "building", "verifying", "succeeded"]


def test_builds_of_other_live_processes_are_not_interrupted(settings):
    import os
    import subprocess

    import sys

    orch = Orchestrator(settings, FakeGemini(manifest()), builder=FakeBuilder(settings))
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        live = orch.store.create(REQ)
        live.update(status="running", owner_pid=other.pid)
        orch.store.save(live)
        dead = orch.store.create(REQ)
        dead.update(status="running", owner_pid=2**22 + 12345)
        orch.store.save(dead)
        Orchestrator(settings, FakeGemini(manifest()), builder=FakeBuilder(settings))
        assert orch.store.get(live["id"])["status"] == "running"
        assert orch.store.get(dead["id"])["status"] == "failed"
        assert os.getpid() != other.pid
    finally:
        other.kill()


def test_theme_mode_defaults_to_system_for_old_manifests():
    from genesis.core.schemas import AppManifest

    m = AppManifest.model_validate_json(manifest().model_dump_json(exclude={"theme_mode"}))
    assert m.theme_mode.value == "system"


def test_gradle_runs_with_resource_limits(settings, tmp_path, monkeypatch):
    import subprocess as sp

    from genesis.core import builder as b

    seen = {}

    class FakeProc:
        stdout = iter(["BUILD SUCCESSFUL\n"])
        returncode = 0
        pid = 999999

        def wait(self):
            return 0

    def fake_popen(cmd, **kw):
        seen["cmd"], seen["env"] = cmd, kw["env"]
        return FakeProc()

    monkeypatch.setattr(sp, "Popen", fake_popen)
    result = AndroidBuilder(settings).run_gradle(tmp_path, tmp_path / "log")
    assert result.ok
    assert seen["cmd"][:2] == ["/bin/sh", "-c"] and "ulimit -c 0" in seen["cmd"][2]
    assert f"ulimit -f {b.GRADLE_MAX_FILE_BLOCKS}" in seen["cmd"][2]
    assert seen["cmd"][3].endswith("gradlew") and "assembleDebug" in seen["cmd"]
    assert "TWILIO_AUTH_TOKEN" not in seen["env"] and "GEMINI_API_KEY" not in seen["env"]
