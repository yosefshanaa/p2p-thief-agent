# Warm-up: reference implementation, 6 sub-games (UNCOUNTED)

**Not a league match** — the opponent is the lecturer's own example implementation
(`rmisegal/Game-P2P-Cop-Chase`, v3.0.0, commit `960499f`) running **unmodified** with
`--stub-llm`, not another team. Nothing was emailed: our side ran `[email] mode = "draft"` to a
test address, and their `[email] enabled = false`.

| | |
|---|---|
| Date | 2026-08-01 |
| Us | `ahk-yosi`, police, `dialect = "reference"`, `alternate_roles`, `handshake_per_sub_game` |
| Them | `Segal-Thief-Team`, thief, reference peer, `--stub-llm` |
| Transport | localhost 8802 ↔ 8801, FastMCP over HTTP |
| Purpose | collect real opponent trajectories for `learn clone` (README §4) |
| Doctrine | the tuned `config/doctrine.json` (19 of 20 fields differ from the defaults) |

## What it produced

**204 labelled decisions** by a real opponent — up from 11 in the July warm-up — now fitted into
`config/opponents/segal-reference.json` and playing in the sparring pool as
`clone:segal-reference` (97% of their moves reproduced).

## Three defects it caught, none of which simulation could have

1. **The enclosure claim voids a series.** We enclosed their thief and claimed the capture; they
   have no such rule, kept playing, never sent their audit package, and sub-game 2 died on
   `both peers claim role 'thief'`. In a counted match: one capture, then five technical losses.
   → `[interop] claim_enclosure`, now a negotiated switch (RUNBOOK §3b).
2. **`HOLD:-` is their STAY, and we were discarding it** — 23 of 35 records in one sub-game. The
   surviving sample contained *no* STAY at all, so a clone fitted on it would have learned an
   opponent that never holds position, while the real one sat on one cell for 27 consecutive
   turns. → `learn/clone_data.py`.
3. **Our squeeze loses points when enclosure is not agreed.** We barred (6,5) and (5,6), their
   thief sat in (6,6) for 27 turns, and our police finished at (6,4) — outside the wall it had
   built. Survival, 5 points where 20 was on offer. → the squeeze now stops one door short
   unless the rule is agreed (`strategy/squeeze.py`).

Defect 3 is the expensive one: it only appears in the configuration we must use against
reference-derived opponents, which is most of the league.

## Reproduce

```bash
# their peer, in a clone of the reference repo
uv run python -m police_thief peer --role thief --stub-llm --no-gui
# ours, started FIRST - their connect window is 60 s
uv run p2p-pursuit peer --role police --config-dir <dir with the [interop] block> \
    --no-gui --games 1
uv run p2p-pursuit learn clone --match matches/warmup-reference-2026-08-01 --name segal-reference
```
