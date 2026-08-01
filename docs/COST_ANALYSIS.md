# COST ANALYSIS — LLM Tokens per Series (guidelines §11, book ch. 9/Appendix F)

The move is always pure Python, so **the entire game logic costs zero tokens**. Tokens are spent
only by the optional banter layer, bounded by the negotiated `[token budget]` (~200,000/series)
and metered per call into the sealed result (`tokens_used`, rule #54).

## Per-series consumption model

One series = 6 sub-games × ≤35 steps/side ⇒ **≤ 420 banter calls** for our side
(`every_n_steps = 1`; raising it divides the count). Measured prompt ≈ 60 input tokens,
completion capped by the 15-word hint ≈ 25 output tokens.

| Provider (`[trash_talk]`) | Where it runs | Tokens/series (≤420 calls) | Cost/series | Rate-limit exposure |
|---|---|---|---|---|
| `template` (default) | in-process | **0** | **$0** | none — offline |
| `ollama` | localhost:11434 | 0 API tokens | $0 (local compute) | none |
| **`openai` (`gpt-5.6-luna`) — configured default** | OpenAI API (or compatible gateway via `base_url`) | **≈ 29k total, measured** (70 tok/call × ≤420) | check the current rate for `gpt-5.6-luna`; `gpt-5.4-nano` is the cheap swap | account RPM; bounded by a 10 s per-call timeout + template fallback |
| `claude_api` (Haiku 4.5) | Anthropic API | ≈ 25k in + 10.5k out | ≈ **$0.08** (at $1/M in, $5/M out) | account RPM; guarded by `step_deadline_seconds` + template fallback |
| `claude_cli` | Claude Code subscription | ≈ 35k equivalent | subscription quota | CLI startup latency ⇒ highest stall risk; fallback covers |

All figures sit far under the 200k budget (≤ 18% in the worst case); a full 10-match league
season on `claude_api` costs under $1.

## Optimization strategies (applied)

1. **Zero-token default** — the shipped configuration plays entire series at $0; competition
   moved to the movement algorithm, exactly as the book intends.
2. **`every_n_steps` throttle** — e.g. 5 cuts LLM calls to ≤84/series (≈$0.016 on Haiku).
3. **Hard word cap in the system prompt** (15 words) bounds output tokens by contract.
4. **Deadline + fallback** — a slow/failed provider degrades to the template mid-step, so cost
   and latency have a ceiling and a turn can never stall on a provider (technical-loss shield).
5. **Model choice** — banter needs no reasoning depth: the smallest cloud model (Haiku) or a
   local 3B via Ollama is strictly sufficient; anything larger buys nothing.

## Budget governance

Consumption is counted per call (`TurnEngine.tokens_used`), sealed into `result_<game_id>.json`,
and declared against the agreed cap in the step-0 declaration — an over-budget series is visible
to the opponent and the grader by construction.

## Measured latency — `openai` / `gpt-5.4` (2026-07-29, WSL; `gpt-5.6-luna` is now the configured model)

Latency, not price, is the binding constraint: a turn that misses its deadline is a
**technical loss**, so banter cost is capped in time as well as tokens.

| Phase | Measured | Where it is paid |
|---|---|---|
| `import openai` + client construction + connection warm-up | ≈ 54 s | **once at peer startup**, outside any turn |
| Banter call, steady state | **1.1 – 2.3 s** | inside the turn (deadline 30 s) |
| Worst case by construction | **10 s** | `call_timeout = deadline // 3`, `max_retries=0` |

Three findings from live testing, each of which would otherwise have failed *silently* —
`produce()` swallows every exception into the template fallback, so a broken provider looks
healthy while reporting 0 tokens forever:

1. **`max_tokens` is rejected by the whole gpt-5.x family** ("Unsupported parameter … use
   `max_completion_tokens`"). Verified against `gpt-5.4` and `gpt-5.6-luna`; older models
   (`gpt-4o-mini`, `gpt-4.1-mini`) accept the new keyword too, so it is used universally.
2. **Reasoning models return an empty message on a small budget** — `gpt-5.6-luna` produced
   *no text* at 60 completion tokens (spent on hidden reasoning) and needed ≈400. The 15-word
   hint cap is therefore enforced by `clip_words`, never by starving the token budget.
3. **The one-off costs must not be paid in the turn loop.** `import openai` alone measured
   ≈31 s and the first request ≈22 s — each larger than the 30 s turn deadline. Both are now
   paid at construction, and SDK retries are disabled so a slow call cannot chain into a stall.
