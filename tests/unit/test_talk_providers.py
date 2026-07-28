"""Banter providers + .env loading.

The invariant that matters for the game: a provider may fail in any way at
all (missing key, missing package, dead network, garbage reply) and the turn
must still produce a legal hint - never raise, never stall (rule #25 keeps
the LLM out of movement, so banter failure can never cost a game).
"""

import random

from p2p_pursuit.shared.env import load_dotenv, parse_env
from p2p_pursuit.strategy.talk_llm import OpenAiTalk, make_talk_provider


def test_parse_env_handles_comments_quotes_and_blanks():
    text = (
        "# a comment\n"
        "\n"
        "OPENAI_API_KEY=sk-test-123       # copied from .env-example\n"
        'QUOTED="hash # inside stays"\n'
        "EMPTY=\n"
        "export EXPORTED=yes\n"
        "malformed-line-without-equals\n"
    )
    env = parse_env(text)
    assert env["OPENAI_API_KEY"] == "sk-test-123"  # inline comment stripped
    assert env["QUOTED"] == "hash # inside stays"  # quoted value kept whole
    assert env["EMPTY"] == ""
    assert env["EXPORTED"] == "yes"
    assert "malformed-line-without-equals" not in env


def test_load_dotenv_never_overrides_real_environment(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("FROM_FILE=file\nALREADY_SET=file\n", encoding="utf-8")
    monkeypatch.setenv("ALREADY_SET", "real")
    loaded = load_dotenv(path)
    import os

    assert os.environ["FROM_FILE"] == "file"
    assert os.environ["ALREADY_SET"] == "real"  # exported env wins over .env
    assert loaded == 1
    assert load_dotenv(tmp_path / "missing.env") == 0  # absent file is fine


def test_factory_selects_openai_and_honours_config():
    provider = make_talk_provider("openai", "gpt-test", 30, "https://gw.example/v1")
    assert isinstance(provider, OpenAiTalk)
    assert provider.model == "gpt-test" and provider.base_url == "https://gw.example/v1"


def test_openai_falls_back_to_template_when_unavailable(monkeypatch):
    """No key configured -> template hint, zero tokens, no exception."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = make_talk_provider("openai", "gpt-test", 1, "")
    text, tokens = provider.produce("north", "New York", 15, random.Random(1))
    assert text and len(text.split()) <= 15
    assert tokens == 0


def test_openai_counts_tokens_and_clips_words(monkeypatch):
    class _Usage:
        prompt_tokens, completion_tokens = 40, 12

    class _Msg:
        content = " ".join(f"w{i}" for i in range(40))

    class _Resp:
        usage, choices = _Usage(), [type("C", (), {"message": _Msg()})()]

    provider = OpenAiTalk("gpt-test", deadline=5)
    monkeypatch.setattr(provider, "_complete", lambda prompt: _Resp())
    text, tokens = provider.produce("south", "New York", 15, random.Random(2))
    assert len(text.split()) == 15  # hint word cap enforced on LLM output
    assert tokens == 52


def test_every_provider_degrades_to_a_legal_hint(monkeypatch):
    """No provider may raise or stall a turn, whatever the backend does.

    Each network/subprocess provider is pointed at a dead endpoint; all must
    return a legal, word-capped hint so a banter outage can never forfeit.
    """
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    dead = "http://127.0.0.1:9"  # reserved discard port: refuses instantly
    providers = [
        make_talk_provider("openai", "m", 1, dead),
        make_talk_provider("ollama", "m", 1, dead),
        make_talk_provider("claude_api", "m", 1, ""),
        make_talk_provider("claude_cli", "", 1, ""),
        make_talk_provider("unknown-provider", "", 1, ""),
    ]
    for provider in providers:
        text, tokens = provider.produce("west", "New York", 15, random.Random(7))
        assert text and len(text.split()) <= 15, provider
        assert tokens == 0, provider
