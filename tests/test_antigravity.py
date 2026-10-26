"""Antigravity bridge: a fake `agentapi` stands in for the desktop app, so no real conversations are started."""

import json
import stat
import textwrap

import pytest
from conftest import manifest

from genesis.config import Settings
from genesis.core import antigravity
from genesis.core.antigravity import AntigravityClient, make_ai_client
from genesis.core.gemini import GeminiClient, GeminiError

FAKE = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, pathlib, sys, uuid
    root = pathlib.Path(os.environ["FAKE_AGY_DIR"])
    calls = root / "calls.jsonl"
    with calls.open("a") as f:
        f.write(json.dumps({{"argv": sys.argv[1:], "project": os.environ.get("ANTIGRAVITY_PROJECT_ID"),
                            "agy_env": sorted(k for k in os.environ if k.startswith("ANTIGRAVITY_"))}}) + "\\n")
    max_len = int(os.environ.get("FAKE_AGY_MAX_PROMPT") or 0)
    if max_len and len(sys.argv[-1]) > max_len:
        import time; time.sleep(60)  # like the real agentapi with a long prompt: never starts a conversation
    replies = json.loads((root / "replies.json").read_text())
    n = sum(1 for _ in calls.open()) - 1
    if n >= len(replies):
        print(json.dumps({{"response": {{}}, "error": "rpc error: connection refused"}}))
        sys.exit(0)
    conv = str(uuid.uuid4())
    logs = root / "brain" / conv / ".system_generated" / "logs"
    logs.mkdir(parents=True)
    steps = [{{"type": "USER_INPUT", "status": "DONE", "content": sys.argv[-1]}}]
    steps += [{{"type": "ERROR_MESSAGE", "status": "DONE", "content": "Error: Your previous response was cut off because "
                "it exceeded the output token limit"}} if r == "CUT" else
              {{"type": "PLANNER_RESPONSE", "status": "DONE", "content": r}} for r in replies[n]]
    (logs / "transcript_full.jsonl").write_text("".join(json.dumps(s) + "\\n" for s in steps))
    if os.environ.get("FAKE_AGY_HANG"):
        import time; time.sleep(60)  # like agentapi blocking after the conversation exists
    print(json.dumps({{"response": {{"newConversation": {{"conversationId": conv}}}}}}))
""")


@pytest.fixture
def agy(tmp_path, monkeypatch, settings):
    d = tmp_path / "agy"
    (d / "brain").mkdir(parents=True)
    exe = d / "agentapi"
    exe.write_text(FAKE.format())
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FAKE_AGY_DIR", str(d))
    monkeypatch.setenv("ANTIGRAVITY_LS_ADDRESS", "127.0.0.1:1")
    monkeypatch.setenv("ANTIGRAVITY_CSRF_TOKEN", "test-token")
    monkeypatch.setattr(antigravity, "POLL_S", 0.01)
    monkeypatch.setattr(antigravity, "SETTLE_S", 0.05)
    monkeypatch.setattr(antigravity, "DIRECT_TIMEOUT_S", 5)
    settings.ai_backend = "antigravity"

    def setup(*replies):
        (d / "replies.json").write_text(json.dumps([list(r) for r in replies]))
        return AntigravityClient(settings, exe=exe, brain_dir=d / "brain", request_dir=d / "requests")

    setup.calls = lambda: [json.loads(x) for x in (d / "calls.jsonl").read_text().splitlines()]
    return setup


def good():
    return manifest().model_dump_json()


def test_generates_app_from_the_agent_reply(agy):
    client = agy([good()])
    m, meta = client.generate_app("A workout log", None)
    assert m.app_name == "Lift Log" and meta["model"].startswith("antigravity")
    call = agy.calls()[0]
    assert call["project"] == "outside-of-project"
    assert not any(a.startswith("--model") for a in call["argv"])  # "app" = whatever is picked in Antigravity
    assert "A workout log" in call["argv"][-1] and "Do NOT use any tools" in call["argv"][-1]


def test_reply_wrapped_in_prose_and_fences(agy):
    client = agy(["Sure! Here it is:\n```json\n" + good() + "\n```\nDone."])
    assert client.generate_app("x", None)[0].app_name == "Lift Log"


def test_invalid_reply_is_retried_with_the_error(agy, settings):
    settings.antigravity_model = "flash"
    client = agy(["not json at all"], [good()])
    m, meta = client.generate_app("x", None)
    calls = agy.calls()
    assert m.app_name == "Lift Log" and meta["attempt"] == 2
    assert "--model=flash" in calls[0]["argv"] and "previous reply was rejected" in calls[1]["argv"][-1]


def test_gives_up_with_a_safe_error(agy):
    client = agy(['{"app_name": 5}'], ["still bad"])
    with pytest.raises(GeminiError, match="did not return a valid AppManifest"):
        client.generate_app("x", None)


def test_unreachable_app(agy):
    client = agy()
    with pytest.raises(GeminiError, match="Is Antigravity open"):
        client.generate_app("x", None)


def test_requires_an_antigravity_terminal(agy, monkeypatch, settings):
    client = agy([good()])
    monkeypatch.delenv("ANTIGRAVITY_CSRF_TOKEN")
    assert not client.configured and "Antigravity terminal" in client.problem()
    with pytest.raises(GeminiError, match="Antigravity terminal"):
        client.generate_app("x", None)
    checks = Settings.doctor(settings)["checks"]
    assert any(c["name"] == "Antigravity bridge" and not c["ok"] for c in checks)


def test_backend_selection(settings):
    assert isinstance(make_ai_client(settings), GeminiClient)
    settings.ai_backend = "antigravity"
    assert isinstance(make_ai_client(settings), AntigravityClient)


def test_parent_agent_variables_are_not_passed_on(agy, monkeypatch):
    monkeypatch.setenv("ANTIGRAVITY_CONVERSATION_ID", "parent-conversation")
    monkeypatch.setenv("ANTIGRAVITY_TRAJECTORY_ID", "parent-trajectory")
    agy([good()]).generate_app("x", None)
    assert agy.calls()[0]["agy_env"] == ["ANTIGRAVITY_CSRF_TOKEN", "ANTIGRAVITY_LS_ADDRESS", "ANTIGRAVITY_PROJECT_ID"]


def test_slow_agentapi_is_found_by_its_tag(agy, monkeypatch):
    monkeypatch.setenv("FAKE_AGY_HANG", "1")
    m, meta = agy([good()]).generate_app("x", None)
    assert m.app_name == "Lift Log" and meta["seconds"] < 30


def test_long_prompt_falls_back_to_a_request_file(agy, monkeypatch):
    monkeypatch.setenv("FAKE_AGY_MAX_PROMPT", "2000")
    client = agy([good()], [good()], [good()])  # the first (direct) call hangs and never uses its reply
    m, _ = client.generate_app("A workout log", None)
    assert m.app_name == "Lift Log" and client.file_mode
    call = agy.calls()[-1]
    assert call["argv"][-2] == "--" and len(call["argv"][-1]) < 2000
    path = call["argv"][-1].split("Read the file ", 1)[1].split(" in full", 1)[0]
    body = open(path, encoding="utf-8").read()
    assert "A workout log" in body and "JSON Schema" in body
    client.generate_app("Another app", None)  # file mode sticks: no second slow direct attempt
    assert len(agy.calls()) == 3


def test_language_server_binary_gets_the_agentapi_subcommand(settings, tmp_path):
    shim = AntigravityClient(settings, exe=tmp_path / "agentapi")
    server = AntigravityClient(settings, exe=tmp_path / "language_server")
    assert shim.base_cmd() == [str(tmp_path / "agentapi")]
    assert server.base_cmd() == [str(tmp_path / "language_server"), "agentapi"]


def test_cut_off_reply_is_retried_with_a_smaller_budget(agy):
    client = agy(['{"app_name": "Big", "files": [{"path": "GenesisApp.kt", "content": "...', "CUT"], [good()])
    m, meta = client.generate_app("x", None)
    assert m.app_name == "Lift Log" and meta["attempt"] == 2
    assert "cut off because it was too long" in agy.calls()[-1]["argv"][-1]
