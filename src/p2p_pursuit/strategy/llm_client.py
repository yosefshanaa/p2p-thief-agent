"""The bounded completion client, and the two env readers everything uses.

Split out of :mod:`.llm_move` so each file stays inside the guidelines' 150-line
limit (§3.2 - split, never compress). This module is the transport only: one
call, one budget, no retries and no policy. The circuit breaker, the meter and
the veto that decide whether to *use* an answer stay in :mod:`.llm_move`.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import urllib.request

#: Providers that can answer a move. `claude_cli` and the template are absent on
#: purpose: a subprocess per turn cannot be made to fit the envelope, and a
#: template has no opinion about a move the doctrine does not already hold.
MOVE_PROVIDERS = ("openai", "ollama")
FAILURES_BEFORE_GIVING_UP = 3
#: Reasoning models spend the budget on hidden reasoning before emitting any
#: text - `talk_llm` measured gpt-5.6-luna returning empty at 60 - and we need
#: one word out of it. Raised from 400 after a live eval saw `empty completion`
#: on 20 of 115 calls: the cap is not what we are billed for (195 tokens/call
#: measured, unchanged at 400, 800, 1500 and 3000), so headroom here is free and
#: running out of it costs a turn.
COMPLETION_BUDGET = 2000


class MoveClient:
    """One bounded completion, or an exception. Never retries, never blocks long."""

    def __init__(self, provider: str, model: str, timeout: int, base_url: str) -> None:
        self.provider, self.model = provider, model
        self.timeout, self.base_url = timeout, base_url
        self._client = None
        self._warm = threading.Thread(target=self._build, daemon=True) \
            if provider == "openai" else None
        if self._warm is not None:
            self._warm.start()

    @property
    def ready(self) -> bool:
        """False until the background warm-up has produced a usable client.

        Measured 2026-08-22 against gpt-5.6-luna: importing the SDK, building
        the client and making the first request cost **35.5 s** on a cold WSL
        filesystem - *longer than the 30 s step deadline*. Brains are built
        lazily by `EngineState._brain_for`, so doing that inline would stall the
        first turn of a match past its own envelope and forfeit the sub-game we
        were trying to protect. It therefore runs on a daemon thread and the
        doctrine plays until it lands, which costs a few early turns and cannot
        cost the game.
        """
        return self._client is not None

    def _build(self) -> None:
        """Import, construct and warm off the turn path. Never raises."""
        try:
            from openai import OpenAI

            client = OpenAI(timeout=self.timeout, max_retries=0,
                            **({"base_url": self.base_url} if self.base_url else {}))
        except Exception:  # noqa: BLE001 - a missing package must not stop the peer
            return
        with contextlib.suppress(Exception):
            client.chat.completions.create(
                model=self.model, max_completion_tokens=COMPLETION_BUDGET,
                messages=[{"role": "user", "content": "Say OK."}])
        self._client = client

    def ask(self, prompt: str) -> tuple[str, int]:
        """Return (text, tokens). Raises on any failure - the caller falls back."""
        if self.provider == "ollama":
            body = json.dumps({"model": self.model or "llama3.2", "stream": False,
                               "prompt": prompt}).encode()
            url = f"{(self.base_url or 'http://localhost:11434').rstrip('/')}/api/generate"
            request = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())["response"].strip(), 0
        if self._client is None:
            raise RuntimeError("openai client unavailable")
        # max_completion_tokens, NOT max_tokens: the gpt-5.x family rejects the
        # latter outright, and the error would be swallowed by our fallback -
        # the brain would look healthy while silently never calling the model.
        response = self._client.chat.completions.create(
            model=self.model, max_completion_tokens=COMPLETION_BUDGET,
            messages=[{"role": "user", "content": prompt}])
        usage = response.usage
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise ValueError("empty completion")
        return text, usage.prompt_tokens + usage.completion_tokens


def int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    return int(raw) if raw.isdigit() else default


def bool_env(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    return raw in ("1", "true", "yes", "on") if raw else default
