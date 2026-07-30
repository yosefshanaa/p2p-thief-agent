# Pre-submission checklist (rules book ch. 11.5 + 11.6)

The book's own final sweep, item by item, against evidence in this repository.
Status is deliberately literal: the book says to verify each item is *actually*
ticked, "not just intended".

## ch. 11.5 — every layer demoed end to end

| # | Book requirement | State | Evidence |
|---|---|---|---|
| 1 | **Base logic** — the engine runs a whole race without crashing; ch. 3 scoring enforced | ✅ | `uv run p2p-pursuit sim --games 6` writes all four artifacts; scoring 20/5 · 5/10 · 2/2 · 0/0 from `config/*/game.json` in `domain/scoring.py`; regression bounds vs. random baselines run in CI |
| 2 | **Public URL** — two agents over FastMCP P2P at a reachable address, not just localhost | ✅ | GATE M5: both peers cross-wired through two public HTTPS tunnels, inbound logged from public IP `89.138.5.166`; `docs/RUNBOOK.md` §6 |
| 3 | **Commit-reveal + audit** — mechanism active, audit finishes with no forgery found | ✅ | `domain/crypto.py` + `domain/audit.py`; both sides reported `Verified OK` over tunnels (M5) and across implementations (`matches/warmup-reference-interop/`); the cheat harness proves each tamper class is caught |
| 4 | **Scent map + belief map** — computed *and influencing decisions* | ✅ | `domain/scent.py` (book figure-4 kernel, golden 0.9→0.81) → `domain/belief.py` → both brains path on the belief argmax; the live GUI renders the heatmap, scent overlay and entropy |
| 5 | **Live GUI + replay app with `Verified OK`** | ✅ | `gui/live_view.py`, `gui/replay_view.py`; screenshots embedded in README §5 (heatmap, `Verified OK`, tamper drill) |
| 6 | **Gmail-API JSON report from BOTH sides**, teams agree the result, each team sends its own | ⚠️ partial | OAuth consent done, `mode = "send"`, verified by a real send (Gmail id `19faaa37fd641748`); auto dual reporting implemented in `peer/runtime_reports.py`. **The both-sides send itself happens only in a counted match** |
| 7 | **GitHub repo with a git tag + academic README** | ⚠️ partial | Both repos public, CI green, README is a full academic manual with the interpretation log. **`v1.0-submission` tag not yet applied** — it is deliberately held until the counted matches are archived, so the tag covers them |
| 8 | **Matches vs. different teams** (≥ the pass minimum, live league) | ❌ blocked | Needs opposing teams to be scheduled — the one genuinely human-blocked item. Interop with reference-derived peers is built and proven, so the remaining risk is scheduling, not code |

## ch. 11.6 — Moodle / GitHub / PDF submission list

| # | Book requirement | State |
|---|---|---|
| a | PRD markdown folder + readable root `README.md` on GitHub; project follows the course's AI-agent software guidelines | ✅ `docs/PRD/` + `docs/PRD.md` + README in both repos; audited against `software_submission_guidelines-V3` (TODO §0) |
| b | Submit via Moodle; share the GitHub code with the lecturer | ⚠️ repos are public (no invite needed); the Moodle upload is human |
| c | **Each member submits separately** | ☐ human |
| d | One unique 8-character group code, no spaces | ✅ `ahk-yosi` |
| e | Fill the Word template **without changing or moving fields**, save as PDF | ☐ human |
| f | Self-grade reflects **code quality only**, never the league result | ☐ human — noted here because it is easy to get wrong |

## What is left, honestly

Only three things, and two of them are human:

1. **Counted matches vs. two different teams** (item 8) — unblocks 6 and 7's timing, plus
   `docs/img/league_match_terminal.png` for README §5.
2. **Tag both repos** `v1.0-submission` once those archives are in.
3. **Moodle**: two separate uploads, template unchanged, self-grade on code quality.
