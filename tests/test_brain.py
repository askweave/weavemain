"""Chat brain: plain conversation through the AI backend, with the server carrying out its decisions."""

import pytest
from test_sms import OWNER, Env

from genesis.core.gemini import GeminiError
from genesis.sms.brain import ChatBrain, ChatDecision


class FakeAI:
    def __init__(self):
        self.decisions = []
        self.contexts = []

    def ask(self, system, user, schema, title="", timeout=None):
        self.contexts.append(user)
        d = self.decisions.pop(0)
        if isinstance(d, Exception):
            raise d
        return d, {"seconds": 0.1}


@pytest.fixture
def env(settings):
    e = Env(settings)
    e.ai = FakeAI()
    e.sms.service.brain = ChatBrain(settings, e.ai, synchronous=True)
    return e


def say(env, text, *decisions):
    env.ai.decisions.extend(decisions)
    env.text(OWNER, text)
    return env.last()


def test_questions_get_real_answers_and_nothing_is_built(env):
    reply = say(env, "can u make websites", ChatDecision(
        reply="Not websites, sorry, I build Android apps. Want an app version of your idea instead?"))
    assert "Android apps" in reply and env.jobs() == []
    assert "New message from the user: can u make websites" in env.ai.contexts[-1]


def test_conversation_then_build_with_the_agreed_spec(env):
    say(env, "i want a new app", ChatDecision(reply="Sure! What should it do?"))
    reply = say(env, "track how much water i drink, with a weekly chart", ChatDecision(
        reply="On it! Building your water tracker.", action="new_app",
        spec="A water intake tracker: log glasses with one tap, daily goal, weekly bar chart, calm blue theme."))
    assert reply.startswith("On it! Building your water tracker. Build ID: G-")
    job = env.jobs()[-1]
    assert "weekly bar chart" in job["prompt"]
    context = env.ai.contexts[-1]
    assert "User: i want a new app" in context and "Sure! What should it do?" in context


def test_change_status_download_and_switch(env):
    say(env, "build me a habit tracker", ChatDecision(reply="Building it!", action="new_app",
                                                      spec="A habit tracker with streaks."))
    env.drain()
    assert "/download/" in say(env, "can i get it on my phone", ChatDecision(reply="", action="download"))
    say(env, "make the buttons bigger", ChatDecision(reply="Sure, making them bigger.", action="change_app",
                                                      spec="Make all buttons larger."))
    assert env.jobs()[-1]["kind"] == "change" and env.jobs()[-1]["change_request"] == "Make all buttons larger."
    # Status questions are answered by the rules instantly, without asking the AI.
    assert env.jobs()[-1]["ref"] in say(env, "how's it going")
    assert env.ai.decisions == []
    assert "Your apps" in say(env, "what have i made", ChatDecision(reply="", action="list_apps"))


def test_server_rules_still_apply(env):
    say(env, "build a habit tracker", ChatDecision(reply="Building!", action="new_app", spec="Habit tracker"))
    reply = say(env, "also build a recipe app", ChatDecision(reply="On it!", action="new_app", spec="Recipe app"))
    assert "still in progress" in reply and len(env.jobs()) == 1  # one build at a time, whatever the model says
    say(env, "change app 7", ChatDecision(reply="ok", action="change_app", spec="x", project=7))
    assert len(env.jobs()) == 1


def test_falls_back_to_rules_when_the_backend_fails(env):
    reply = say(env, "hi", GeminiError("Antigravity did not answer"))
    assert ("Weave" in reply or "Genesis" in reply) and env.jobs() == []


def test_commands_skip_the_brain(env):
    env.text(OWNER, "STATUS")
    assert env.ai.contexts == [] and "No builds yet" in env.last()


def test_rules_handle_the_reported_conversation(settings):
    """Without the brain: a question isn't an idea, and 'i want new app' asks what it should do."""
    env = Env(settings)
    env.text(OWNER, "Build me a habit tracker with streaks")
    env.drain()
    env.text(OWNER, "can u make websites")
    assert "not websites" in env.last() and len(env.jobs()) == 1
    env.text(OWNER, "i want new app")
    assert "What should it do?" in env.last() and len(env.jobs()) == 1
    env.text(OWNER, "a water tracker with a weekly chart")
    assert len(env.jobs()) == 2 and "water" in env.jobs()[-1]["prompt"]
