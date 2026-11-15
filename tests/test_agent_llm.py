"""LLM agent loop with a mocked Anthropic client (no network, no credentials)."""

from types import SimpleNamespace

import anthropic

from backend.agents import agent
from backend.config import settings


class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.script.pop(0)


def block(**kw):
    return SimpleNamespace(**kw)


def test_llm_loop_executes_validated_tools(db, monkeypatch):
    script = [
        SimpleNamespace(stop_reason="tool_use", content=[
            block(type="thinking", thinking=""),
            block(type="tool_use", id="t1", name="analyze_terrain",
                  input={"site_id": "mars-gale"}),
            block(type="tool_use", id="t2", name="analyze_terrain",
                  input={"site_id": "BAD ID"}),
        ]),
        SimpleNamespace(stop_reason="end_turn", content=[
            block(type="text", text="Gale's mean slope comes from MOLA MEGDR.")]),
    ]
    fake = FakeMessages(script)
    monkeypatch.setattr(anthropic, "Anthropic",
                        lambda **_: SimpleNamespace(beta=SimpleNamespace(messages=fake)))
    monkeypatch.setattr(type(settings), "llm_enabled", property(lambda self: True))

    reply = agent.chat(db, "Describe Gale terrain")
    assert reply.mode == "llm"
    assert reply.answer.startswith("Gale's mean slope")
    assert [c["ok"] for c in reply.tool_calls] == [True, False]
    # Second request carries the full assistant content and both tool results.
    second = fake.calls[1]["messages"]
    assert second[-2]["role"] == "assistant"
    results = second[-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert results[1]["is_error"] is True
    assert fake.calls[0]["model"] == settings.llm_model
    assert fake.calls[0]["fallbacks"] == "default"
    assert "tool_choice" not in fake.calls[0]


def test_llm_failure_falls_back_to_deterministic(db, monkeypatch):
    def boom(**_):
        raise anthropic.APIConnectionError(request=None)

    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(create=boom))))
    monkeypatch.setattr(type(settings), "llm_enabled", property(lambda self: True))
    reply = agent.chat(db, "list candidate locations")
    assert reply.mode == "deterministic" and "LLM unavailable" in reply.notice
