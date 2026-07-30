# Warm-up: interop vs. the reference implementation (UNCOUNTED)

Evidence for `docs/RUNBOOK.md` §3b. **Not a league match** — the opponent is the lecturer's
own example implementation (`rmisegal/Game-P2P-Cop-Chase`, v3.0.0) running **unmodified**,
not another team. No result was emailed (`[email] mode = "draft"` to a test address).

| | |
|---|---|
| Date | 2026-07-29 |
| Us | `ahk-yosi`, police, `[interop] dialect = "reference"` |
| Them | `segal-thief-team`, thief, reference peer with `--stub-llm` |
| Transport | localhost (8802 ↔ 8801), FastMCP over HTTP |
| Sub-games | 1, played to the 35-step survival threshold |
| Banter | `template` (0 tokens) |

## Outcome — both sides agreed

| Direction | Verdict | Score |
|---|---|---|
| Their audit of **our** log (`theirs/result_*.json`) | `log_verified: true`, `tampered: false` | thief 10 |
| Our audit of **their** log (`ours/log_*.json`) | `Verified OK` | police 5 |

This is the claim that matters: an **unmodified reference peer verified our commit-reveal
records**, because interop mode seals them with their digest (`canonical(payload)|nonce`) and
reveals them in their `{payload, nonce, commit}` envelope.

`ours/result_*.json` reports `mutual_agreement: false` — correctly. Their `submit_audit`
returns `{"ok": true}` and keeps their verdict local, so we never received it, and claiming
agreement we did not receive would put an unverified assertion into a signed artifact.

## Two defects this warm-up caught

1. Their reporting crashed *after* a completed game — our identity payload omitted
   `mcp_servers` / `llm_model` / `spec`, which their `group_block` indexes directly.
2. Our replay viewer stamped this clean match `TAMPERED`, re-hashing their envelopes as if
   they were our sealed records.

Both are fixed and pinned by `tests/integration/test_interop_bridge.py`.

## Reproduce

```bash
# their peer (in a clone of the reference repo)
uv run python -m police_thief peer --role thief --stub-llm --no-gui
# ours, started FIRST - their connect window is 60 s
uv run p2p-pursuit peer --role police --config-dir <dir with [interop] dialect="reference"> \
    --no-gui --games 1
```
