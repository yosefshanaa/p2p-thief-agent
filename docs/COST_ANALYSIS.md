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
