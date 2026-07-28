"""Optional LLM banter providers: ollama / claude_api / claude_cli (book table 21).

Strictly verbal - the move is decided before any of this runs. Every provider
falls back to the zero-token template on any failure, so a flaky LLM can
never stall or influence a turn. Token usage is metered for the budget seal.
"""

from __future__ import annotations

import json
import random
import subprocess
import urllib.request

from ..domain.hints import clip_words
from .talk_template import TemplateTalk

PROMPT = (
    "You are the banter voice of a {role} agent in a pursuit game set in {area}. "
    "Write ONE taunting sentence of at most {max_words} words claiming to be in the "
    "{region} area. No coordinates or numbers."
)


DEFAULT_OLLAMA = "http://localhost:11434"


class OllamaTalk:
    name = "ollama"

    def __init__(self, model: str, deadline: int = 30, base_url: str = "") -> None:
        self.model, self.deadline = model or "llama3.2", deadline
        self.url = f"{(base_url or DEFAULT_OLLAMA).rstrip('/')}/api/generate"
        self._fallback = TemplateTalk()

    def produce(self, region: str, map_area: str, max_words: int,
                rng: random.Random) -> tuple[str, int]:
        try:
            body = json.dumps({
                "model": self.model, "stream": False,
                "prompt": PROMPT.format(role="game", area=map_area or "an old city",
                                        max_words=max_words, region=region),
            }).encode()
            req = urllib.request.Request(
                self.url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.deadline) as resp:
                text = json.loads(resp.read())["response"].strip()
            return clip_words(text, max_words), 0  # local model: zero API tokens
        except Exception:
            return self._fallback.produce(region, map_area, max_words, rng)


class ClaudeApiTalk:
    name = "claude_api"

    def __init__(self, model: str, deadline: int = 30) -> None:
        self.model, self.deadline = model or "claude-haiku-4-5-20251001", deadline
        self._fallback = TemplateTalk()

    def produce(self, region: str, map_area: str, max_words: int,
                rng: random.Random) -> tuple[str, int]:
        try:
            import anthropic

            client = anthropic.Anthropic(timeout=self.deadline)
            msg = client.messages.create(
                model=self.model, max_tokens=60,
                messages=[{"role": "user", "content": PROMPT.format(
                    role="game", area=map_area or "an old city",
                    max_words=max_words, region=region)}],
            )
            tokens = msg.usage.input_tokens + msg.usage.output_tokens
            return clip_words(msg.content[0].text.strip(), max_words), tokens
        except Exception:
            return self._fallback.produce(region, map_area, max_words, rng)


class OpenAiTalk:
    """OpenAI (or any OpenAI-compatible gateway via ``base_url``).

    The key is read from OPENAI_API_KEY in the environment - never from
    config/, never from an argument, so it cannot reach a repo or a sealed
    record. Any failure degrades to the zero-token template.
    """

    name = "openai"

    def __init__(self, model: str, deadline: int = 30, base_url: str = "") -> None:
        self.model = model or "gpt-4o-mini"
        self.deadline, self.base_url = deadline, base_url
        self._fallback = TemplateTalk()

    def _complete(self, prompt: str):
        from openai import OpenAI

        client = OpenAI(timeout=self.deadline, **({"base_url": self.base_url}
                                                  if self.base_url else {}))
        return client.chat.completions.create(
            model=self.model, max_tokens=60,
            messages=[{"role": "user", "content": prompt}])

    def produce(self, region: str, map_area: str, max_words: int,
                rng: random.Random) -> tuple[str, int]:
        try:
            response = self._complete(PROMPT.format(
                role="game", area=map_area or "an old city",
                max_words=max_words, region=region))
            usage = response.usage
            tokens = usage.prompt_tokens + usage.completion_tokens
            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise ValueError("empty completion")
            return clip_words(text, max_words), tokens
        except Exception:
            return self._fallback.produce(region, map_area, max_words, rng)


class ClaudeCliTalk:
    name = "claude_cli"

    def __init__(self, model: str = "", deadline: int = 30) -> None:
        self.deadline = deadline
        self._fallback = TemplateTalk()

    def produce(self, region: str, map_area: str, max_words: int,
                rng: random.Random) -> tuple[str, int]:
        try:
            out = subprocess.run(
                ["claude", "-p", PROMPT.format(role="game", area=map_area or "an old city",
                                               max_words=max_words, region=region)],
                capture_output=True, text=True, timeout=self.deadline)
            text = out.stdout.strip()
            if out.returncode != 0 or not text:
                raise RuntimeError(out.stderr[:200])
            return clip_words(text, max_words), max(1, len(text) // 4)
        except Exception:
            return self._fallback.produce(region, map_area, max_words, rng)


def make_talk_provider(provider: str, model: str, deadline: int, base_url: str = ""):
    """Factory keyed by the private ``[trash_talk] provider`` setting."""
    if provider == "ollama":
        return OllamaTalk(model, deadline, base_url)
    if provider == "openai":
        return OpenAiTalk(model, deadline, base_url)
    if provider == "claude_api":
        return ClaudeApiTalk(model, deadline)
    if provider == "claude_cli":
        return ClaudeCliTalk(model, deadline)
    return TemplateTalk()
