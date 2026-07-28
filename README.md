# p2p-pursuit — Distributed Cops-and-Robbers over a Peer-to-Peer Network

> **Role of this repository: THIEF agent** — `uv run p2p-pursuit peer` defaults to `--role thief` here (`ROLE` marker). Sister (police) repository: https://github.com/yosefshanaa/p2p-police-agent

Final project for Dr. Yoram Segal's **"Orchestration of AI Agents"** course, University of Haifa
(rules book `police_thief_p2p.pdf` **v3.0.0**, bundled in the reference repo
[`rmisegal/Game-P2P-Cop-Chase`](https://github.com/rmisegal/Game-P2P-Cop-Chase)).

Two fully autonomous, symmetric AI peers — a **Police** and a **Thief** — chase each other on a
7×7 grid with **no referee and no central server**. Each peer is simultaneously a **FastMCP
server and client**. Neither side ever sees the opponent: each fuses the opponent's decaying
**pheromone field** with free-language **hints that may lie** into a **Bayesian belief map**.
Honesty is enforced by mathematics: every step is sealed with **SHA-256 commit → acknowledge →
reveal → mutual audit**; any tampering is a technical loss, no appeal.

**Team `ahk-yosi`** — Yosef Shanaa (`213314859`) · Ahmad Kaiss (`325811255`).
**Sister repositories** (submission split, book rule #49): police repo
<https://github.com/yosefshanaa/p2p-police-agent> · thief repo
<https://github.com/yosefshanaa/p2p-thief-agent> — both published from this codebase by
`scripts/sync_repos.py`; each carries a `ROLE` marker that sets its default `peer` role.

---

## Table of contents

1. [The game as a Dec-POMDP](#1-the-game-as-a-dec-pomdp)
2. [Architecture & FastMCP orchestration dilemmas](#2-architecture--fastmcp-orchestration-dilemmas)
3. [Strategies implemented](#3-strategies-implemented)
4. [Reinforcement learning](#4-reinforcement-learning)
5. [Screenshots](#5-screenshots)
6. [Status](#6-status)
7. [Installation](#7-installation)
8. [Usage](#8-usage)
9. [Configuration guide](#9-configuration-guide)
10. [How a turn works](#10-how-a-turn-works)
11. [Repository layout](#11-repository-layout)
12. [Documentation map](#12-documentation-map)
13. [Interpretation log](#13-interpretation-log-academic-freedom-book-p-5)
14. [Secrets & Gmail](#14-secrets--gmail)
15. [League play & submission](#15-league-play--submission)
16. [Contributing](#16-contributing)
17. [License & credits](#17-license--credits)

---

## 1. The game as a Dec-POMDP

The system is a two-agent **decentralized partially observable Markov decision process**
⟨I, S, {A_i}, T, {R_i}, {Ω_i}, {O_i}, h⟩:

- **Agents** `I = {Police, Thief}` — no third party exists at runtime; every rule the referee
  would enforce is replaced by cryptography (§2, dilemma D1).
- **State** `S`: both positions, the barrier set (police quota 14), both pheromone fields
  `τ_P, τ_T ∈ [0, 0.9]^{7×7}`, step counter, and protocol phase. *Neither agent ever holds `S`* —
  each holds only its own half plus a belief over the other's.
- **Actions** `A_i`: `{N, S, E, W, STAY}` (no diagonals); the police may instead forfeit the
  move to place a barrier on its own or a 4-adjacent cell (truthfully declared, permanent).
  Alongside the move, each agent chooses a **free-language hint** (≤15 words, *may lie*) with a
  sealed truth-intent flag — the hint channel is itself part of the action space.
- **Transition** `T`: deterministic movement/blocking; pheromone dynamics are fixed and public —
  5×5 emission kernel (focal 0.9) then multiplicative decay `ρ = 0.10` (0.9 → 0.81), locked
  before play by an exchanged hash of the model document.
- **Observations** `Ω_i, O_i`: own state, the opponent's **served scent field** (pre-emission,
  so the freshest visible cell ≈0.81 marks where the opponent *was*), the opponent's hint
  (adversarial channel), and protocol events — barrier declarations, capture claims (a claim
  legitimately leaks the claimant's cell), and denied claims as negative evidence.
- **Rewards** `R_i`: capture 20/5, survival at 35 steps 5/10, tie 2/2, proven tamper 0/0
  (both zeroed). A match is a best-of-6-sub-game series; horizon `h` = 35 steps per sub-game.
- **Belief state**: each peer maintains an exact discrete Bayes filter over the 49 cells —
  scent likelihood (`τ^8` sharpness) → motion-model diffusion → trust-weighted hint update,
  with a trust coefficient driven by a contradiction detector (`domain/belief.py`,
  `domain/trust.py`). The brains (§3) act on this belief, never on ground truth.

## 2. Architecture & FastMCP orchestration dilemmas

```mermaid
flowchart LR
    subgraph PeerA["Police peer (port 8802)"]
        A_GUI[Live GUI\nbelief heatmap] --> A_SDK
        A_SDK[PursuitSDK] --> A_RT[PeerRuntime\nstate machine + watchdog]
        A_RT --> A_ENG[TurnEngine\ncommit/reveal/audit]
        A_ENG --> A_BR[PoliceBrain v3]
        A_ENG --> A_BEL[Belief map + trust]
        A_RT --> A_GK[Gatekeeper] --> A_MAIL[Gmail reporter]
    end
    subgraph PeerB["Thief peer (port 8801)"]
        B_ENG[TurnEngine] --> B_BR[ThiefBrain v3]
    end
    A_RT <-->|"FastMCP HTTP:\nhandshake · receive_commit ·\nreceive_reveal · receive_event ·\naudit_exchange"| B_ENG
    A_MAIL -->|result JSON| L[rmisegal+uoh26finalgame@gmail.com]
```

Full C4, state-machine and sequence diagrams: [`docs/PLAN.md`](docs/PLAN.md) §2. The dilemmas a
referee-less FastMCP orchestration forces, and how this project resolves them:

- **D1 — Who is the referee?** Nobody. Every judgment call (legality, capture, scoring) is made
  twice, independently, and reconciled by the **mutual audit**: after each sub-game the peers
  exchange full sealed logs (nonces included) and re-verify every hash, move legality, scent
  arithmetic and claim answer. One mismatch ⇒ `TAMPERED` ⇒ 0/0.
- **D2 — Symmetric server *and* client.** Each peer must serve MCP tools while calling the
  opponent's. Startup order is unknowable ⇒ retry-until-up connection, `health_check` probes,
  and a handshake that locks a byte-identical constitution by `config_sha256` (refuse on
  mismatch) before any turn.
- **D3 — Turn-taking without a shared clock.** Strict alternation is enforced by an explicit
  state machine (illegal transitions rejected), a per-turn deadline tracker, and a watchdog:
  silence past `turn_timeout_seconds` is a technical loss, persisted before shutdown.
- **D4 — Cross-peer record ordering races.** Two HTTP clients interleave: a capture claim sent
  *after* a reveal once misaligned positional audit pairing and produced a false `TAMPERED`.
  Resolved structurally — claims ride *inside* the reveal (the answer returns atomically in the
  reveal response) and the audit pairs records **content-addressed by digest**, not by position.
- **D5 — Information-release fairness.** A naive reveal of moves would collapse partial
  observability (interpretation #1, §13). The per-step reveal discloses only the public
  projection; moves, positions, intents and nonces stay sealed until the audit — binding first,
  disclosure last.
- **D6 — External-service discipline.** Every outbound call (Gmail, LLM banter) passes a
  **Gatekeeper**: daily quota + token bucket + DoS lock, with a bounded FIFO overflow queue
  (backpressure, never silent drops) and versioned limits in `config/<role>/rate_limits.json`.

## 3. Strategies implemented

The graded core. Full doctrine, tuning history and evaluation evidence:
[`docs/STRATEGY.md`](docs/STRATEGY.md).

**Police v3 — scent-trail-velocity interception.** The freshest scent cell marks where the
thief *was*; consecutive freshest cells yield a velocity estimate, and the brain solves a small
pursuit curve to step toward where the thief *will be* (lookahead k ∈ 0..4). Claims are
disciplined — a claim leaks our exact cell, so we claim only at belief ≥ 0.15, kill-shot
directly at ≥ 0.30, and spend barriers to seal corners at ≥ 0.20 (desperation lowers the bar in
the last 8 steps). Flood-fill vetoes self-trapping barrier placements.

**Thief v3 — claim-radius risk avoidance.** The thief scores candidate cells by the police's
*projected* belief mass within claim range (BFS ≤ 2), forward-projects the interceptor one step,
jukes only when actually being chased (run ≥ 2 closing steps at distance ≤ 3 — always-on zigzag
measurably hurts), avoids corners in the first half, never STAYs, and tells **scent-consistent
lies**: hints that fit what the police can already smell, but bend the inferred direction.

**Evidence (CI-gated, cross-version validated):** the v3 thief cuts the previous-generation
police's captures 16 → 11 over the standard 12-seed tournament; v3 police vs v3 thief lands
54/144 captures (37.5%, vs 25% score break-even); police captures a random walker 27/30; thief
survives a random police 30/30. Reproduce a parameter study with
`uv run python notebooks/strategy_sweep.py`.

## 4. Reinforcement learning

**Not used — by design.** The move policy is deterministic, auditable Python over an exact
Bayes filter (the book's requirement that the move never comes from an LLM is honored — the LLM,
when enabled at all, only writes banter). Strategy quality was driven by a measured
tune-evaluate loop (seeded cross-version tournaments, regressions reverted on evidence) rather
than gradient learning, so the "RL learning curves" README component does not apply. The
sub-game-level *trust coefficient* does adapt online, but it is a Bayesian update, not RL.

## 5. Screenshots

*(Mandatory evidence. The first three were captured live on this codebase — a real two-peer
match over localhost MCP and the replay/tamper drill; the league terminal shot lands during
the first counted match.)*

### Live GUI — Bayesian belief heatmap (local truth only)

![Live belief heatmap: police peer mid-match](docs/img/live_belief_heatmap.png)

Police peer during sub-game 5 of a live two-peer match (`uv run p2p-pursuit peer --role
police`, thief running as a separate process). Red mass = posterior over the thief's cell
after fusing scent + hints; **the opponent's true position is never rendered** (rule #8–9).
Violet cell outlines are the opponent's served **scent trace** (the 5×5 emission block is
clearly visible), the dark-red ring marks the **belief argmax** — here the police is
standing on it — and the side panel reports `belief peak @ (5, 5)  entropy 3.56 bits`
alongside the sent/received hint feed (the thief's contradictory hints have collapsed hint
trust to 0.05, so the belief leans on scent). Green `YOUR TURN` banner, (row, col)
coordinate labels matching the logs, and the color legend strip round out the frame.

### Replay viewer — sealed log verifies clean

![Replay viewer with green Verified OK stamp](docs/img/replay_verified_ok.png)

`uv run p2p-pursuit replay --log <match>/log_*_g01.json` — frame 35/58 of a finished
sub-game. Every step re-hashes against its sealed commit; the green banner is the whole-log
verdict, the per-frame `[Verified OK]` stamp is that step's re-check. The header pins the
match identity (game id, sub-game, perspective, agreed `config_sha256` prefix); the timeline
is scrubbed with the slider, the `|< << >> >|` buttons, arrow keys, or auto-play at
0.5×–4×. Post-game replay is the only place both trajectories are legitimately visible.

### Replay viewer — tamper drill catches a forged record

![Replay viewer with red TAMPERED banner](docs/img/replay_tampered.png)

Same log, one field doctored: the thief's step-10 `pos_after` was forged to the far corner.
The SHA-256 re-hash mismatches its commit at frame 19 — red `TAMPERED` banner, per-frame
`[TAMPERED]` stamp, and the headless run exits with code 3 (`"verdict": "TAMPERED"`).
A forged match is void: technical loss 0/0, no appeal (rule #20).

### Pending until the first counted match

| Evidence | File | How it is captured |
|---|---|---|
| League match terminal + Gmail send id | `docs/img/league_match_terminal.png` | counted-match run |

## 6. Status

| Layer (book §10.3) | State |
|---|---|
| 1. Base logic — board, 4-orthogonal moves, barriers, capture, scoring | ✅ implemented + tested |
| 2. FastMCP P2P infra — peer server+client, state machine, deadline tracker, watchdog | ✅ |
| 3. Strategy module — `BrainBase` plug-in, police/thief doctrine, sim lab | ✅ |
| 4. Language + scent — emission/decay, belief map, trust model, 4 banter providers | ✅ |
| 5. Cloud exposure — public-URL config, smoke probe, [`docs/RUNBOOK.md`](docs/RUNBOOK.md), CI chaos drills (latency / dead link / silence) | ✅ code / ☐ live tunnel drill |
| 6. Crypto — commit-reveal, nonces, mutual audit, step-0 declaration, locks | ✅ |
| 7. Reporting + GUI — 4 JSON artifacts, Gatekeeper, Gmail (draft/send), live GUI, replay verifier | ✅ |

**Quality gate:** 89 tests, coverage ≥94% (gate 85%), Ruff clean (E/F/W/I/N/UP/B/C4/SIM),
every file ≤150 code lines, CI on every push. League play vs. real opposing teams and the
two-repo submission split are still ahead (see [`docs/TODO.md`](docs/TODO.md) §8–9).

## 7. Installation

**System requirements:** Python ≥ 3.13, [`uv`](https://docs.astral.sh/uv/) (the only package
manager used — never pip/venv directly), Linux/WSL2/macOS/Windows; Tk only for the GUIs
(headless works everywhere); no LLM, key or network needed for the default game.

```bash
git clone https://github.com/yosefshanaa/final_Project && cd final_Project
uv sync                     # core + dev from the lockfile
uv sync --extra gmail       # + Google libs (only for real report sending)
uv sync --extra llm         # + anthropic SDK (only for claude_api banter)
uv sync --extra analysis    # + matplotlib (only for the sweep charts)
```

**Environment variables:** copy `.env-example` → `.env` and fill in only what you use
(`ANTHROPIC_API_KEY` for `claude_api` banter; nothing for the default template mode).

**Troubleshooting:** `Address already in use` → a stale peer holds 8801/8802, kill it or change
`my_port`; GUI fails under WSL → run `--no-gui` (or install an X server); Gmail
`invalid_grant` → rerun `uv run p2p-pursuit authorize` (Testing-mode refresh tokens expire);
opponent unreachable → `uv run p2p-pursuit smoke <their-url>` and check the tunnel.

## 8. Usage

```bash
# In-process series (tactics lab / demo) - 6 sub-games, artifacts + result JSON:
uv run p2p-pursuit sim --seed 42

# Two real peers over FastMCP HTTP (two terminals; start order doesn't matter):
uv run p2p-pursuit peer --role thief  --no-gui   # terminal 1 (port 8801)
uv run p2p-pursuit peer --role police --no-gui   # terminal 2 (port 8802)
# drop --no-gui for the live Tkinter belief-heatmap GUI (turn banner, hints feed)

# Verify + view a sealed log (green "Verified OK" / red TAMPERED; exit 3 on tamper):
uv run p2p-pursuit replay --log results/sim-*/log_*_g01.json --no-gui

# Probe a (remote) peer endpoint / one-time Gmail consent:
uv run p2p-pursuit smoke http://127.0.0.1:8801/mcp
uv run p2p-pursuit authorize
```

Flags: `--games N` (dev override; counted matches force 6), `--seed` (reproducibility),
`--counted --prior-counted K` (league match + truthful game-count declaration), `--out DIR`
(artifact location), `--config-dir DIR` (non-default role directory). Typical league workflow:
warm-up → negotiate constitution → `peer --counted` → archive artifacts → both teams' reports
go out automatically ([`docs/RUNBOOK.md`](docs/RUNBOOK.md) is the step-by-step).

## 9. Configuration guide

| File | Role | Key parameters |
|---|---|---|
| `config/<role>/game.json` | **shared constitution** — byte-identical for both teams, SHA-256-locked at handshake | board/starts/first-mover; barrier quota 14; move cap + survival 35; scoring 20/5, 5/10, tie 2; pheromone constants (fixed); league + timer params |
| `config/<role>/game.toml` | private per-peer, never crosses the wire | `my_port`, `opponent_url`, `turn_timeout_seconds`; `[strategy]` brain classes; `[trash_talk] provider/every_n_steps`; `[llm]`; `[email] recipient/mode` |
| `config/<role>/rate_limits.json` | versioned Gatekeeper defaults (constitution section overrides) | rpm 30, retries, queue depth 100, daily quota |
| `config/logging_config.json` | Python logging tree | level, format |

Shared values are negotiated per match (minimums may only rise); a per-match copy of the agreed
constitution is written into the artifacts and archived under `matches/`.

## 10. How a turn works

**observe** (opponent's served scent + hint) → **belief update** (scent likelihood → motion
diffusion → trust-weighted hint) → **brain decides** move / barrier + hint + intent →
**commit** (SHA-256 of the sealed record) → opponent **ack** → **reveal** (public projection
only: hint, scent, barrier declarations — moves stay sealed until the audit) → **log**. After
both moved, every scent field decays (ρ=0.10). Capture claims ride inside the reveal and get
a cryptographically bound truthful answer; barrier-capture and enclosure force honest
confessions; survival at 35 steps ends the sub-game. After every sub-game both peers exchange
full sealed logs (nonces included) and **audit each other** — one mismatch = `TAMPERED` = 0/0.

## 11. Repository layout

```
src/p2p_pursuit/
  sdk/        PursuitSDK - single business-logic entry point (CLI/GUI go through it)
  domain/     board, rules, scoring, scent, belief, trust, hints,
              crypto, protocol, audit, declarations, negotiation, brains_base
  strategy/   police_brain, thief_brain, pathing, talk_template, talk_llm
  peer/       engine_state, turn_engine, service, runtime(+reports), local_match,
              state_machine, deadline, watchdog, log_manager, audit_bridge
  infra/      mcp_server, mcp_client, transport, email_sender
  report/     artifacts (declaration/config/log/result), results
  gui/        live_view (belief heatmap + banner), replay_view, replay_data, view_model
  shared/     config (JSON constitution + private TOML), gatekeeper, rate_limiter, sysinfo
config/police/  config/thief/   # byte-identical game.json + role-private game.toml
matches/     # tracked per-match artifact archive (configs, logs, results)
tests/unit/  tests/integration/ # 89 tests incl. real MCP round-trip + cheat harness
docs/        PRD, PRD/1..7, PLAN, TODO, STRATEGY, GAP_ANALYSIS, RUNBOOK, PROMPT_BOOK, COST_ANALYSIS
```

## 12. Documentation map

| Doc | What |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) + [`docs/PRD/`](docs/PRD/) | Master requirements, 55-rule map, binding parameters, seven stage PRDs |
| [`docs/PLAN.md`](docs/PLAN.md) | Architecture, mermaid diagrams, ADRs, reuse map, milestones, risks |
| [`docs/STRATEGY.md`](docs/STRATEGY.md) | The graded core: doctrine + evaluation numbers |
| [`docs/TODO.md`](docs/TODO.md) | Task tracking with milestone gates |
| [`docs/GAP_ANALYSIS.md`](docs/GAP_ANALYSIS.md) | HW6 vs. final-project spec |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Tunnel + league match operations, interop with reference-derived peers |
| [`docs/PROMPT_BOOK.md`](docs/PROMPT_BOOK.md) | Prompt-engineering log (guidelines §8.3) |
| [`docs/COST_ANALYSIS.md`](docs/COST_ANALYSIS.md) | LLM token/cost model per banter provider |

## 13. Interpretation log (academic freedom, book p. 5)

Decisions where the book under-specifies or contradicts itself — documented as required:

1. **Per-step Reveal discloses the public projection only** (hint, served scent field, barrier
   declaration). Moves, positions, intent and nonces are revealed at the **sub-game audit**.
   Figure 6's "Reveal: Move + Hint" read literally would make positions fully computable from
   the known starts and collapse the partial-observability premise of ch. 1/4/6; the
   lecturer's reference implementation resolves it the same way.
2. **First mover = thief**, agreed at handshake (the book never fixes it).
3. **Capture-claim semantics**: the police's claim is a query ("I am at X — are you here?");
   only the thief's sealed truthful answer constitutes the capture event. The claim itself
   legitimately leaks the police position — its strategic price. Claims ride inside the reveal
   so cross-peer record ordering can never race.
4. **Scent serving is pre-emission**: each step serves the field *before* that step's deposit,
   so the freshest visible cell is ≈0.81 — exactly the book's ch. 4.4 worked example — and the
   opponent sees where you *were*, never where you are.
5. **τ is clamped to [0, 0.9]** (the book's stated range) since additive re-emission would
   otherwise exceed the focal cap; decay ticks are applied per own-step (equivalent to
   full-turn decay under strict alternation, and exactly reproducible in the audit).
6. **A fifth banter provider (`openai`) extends the book's table 21** (template / Ollama /
   `claude_api` / `claude_cli`). The table enumerates providers the book anticipated, not a
   closed set: rule #25 constrains *what* the LLM may do (never decide a move — banter only),
   not which vendor generates the text. The provider is therefore additive and rule-compliant,
   and every provider shares one contract — a hard word cap, a step deadline, metered tokens,
   and an unconditional fall back to the zero-token template, so no backend can stall a turn
   (unit-tested for all five). API keys live only in a git-ignored `.env`, never in `config/`,
   because config files are exchanged with the opponent and hashed into `config_sha256`.

## 14. Secrets & Gmail

`credentials.json` / `token.json` (Gmail OAuth, send-only scope) are git-ignored and never
committed. The client credentials are reused from HW6; the refresh token needs a **one-time
interactive consent**:

```bash
uv run p2p-pursuit authorize     # browser consent -> writes token.json
```

Then set `[email] mode = "send"` in `config/<role>/game.toml` for league matches. Without a
valid token (or in `draft` mode) the reporter runs dry-run and says so - a send-only scope
cannot create real Gmail drafts, so `draft` means "build the MIME locally, do not call Gmail".

## 15. League play & submission

A counted match requires: negotiated byte-identical constitution, scent-model lock exchange,
truthful prior-counted declaration, 6 sub-games, mutual audit, result agreement, and **both
teams reporting independently** to `rmisegal+uoh26finalgame@gmail.com` — a missing report
forfeits that side's points. ≥2 counted matches vs different teams (≤10 total, one counted per
opponent). Per-match artifacts + the agreed config are archived under `matches/` and committed;
the declaration and result artifacts carry the exact git commit hash that played. Submission:
this codebase publishes to **two cross-linked repos** (police / thief), each with README +
`/config` + PRD/PLAN/TODO, tagged `v1.0-submission`. Step-by-step:
[`docs/RUNBOOK.md`](docs/RUNBOOK.md); checklist: [`docs/TODO.md`](docs/TODO.md) §8–9.

## 16. Contributing

Quality gates every change must keep green (CI enforces): `uv run ruff check` — zero violations
(E/F/W/I/N/UP/B/C4/SIM); `uv run pytest --cov` — coverage ≥ 85%; every source/test file ≤ 150
code lines (split, never compress); TDD — a new module ships with its `tests/` mirror; all
business logic behind the `PursuitSDK` facade; every external call behind the Gatekeeper; all
tunables from `config/` — nothing hard-coded; English-only comments explaining *why*, not *what*.
Branch off `master`, keep commits scoped, update `docs/` with the change.

## 17. License & credits

MIT (see `pyproject.toml`). Assignment and rules book: **Dr. Yoram Segal**, "Orchestration of
AI Agents", University of Haifa; public reference simulation:
[`rmisegal/Game-P2P-Cop-Chase`](https://github.com/rmisegal/Game-P2P-Cop-Chase) (studied as a
learning aid per its license — our implementation and strategies are original). Third-party
libraries under their own licenses: [FastMCP](https://gofastmcp.com/), Google API client +
auth libs (Gmail), optional [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python)
/ [Ollama](https://ollama.com), and the toolchain — [uv](https://docs.astral.sh/uv/),
[Ruff](https://docs.astral.sh/ruff/), [pytest](https://pytest.org/),
[Matplotlib](https://matplotlib.org/) (analysis extra). Built with Claude Code; the full
prompt-engineering log is in [`docs/PROMPT_BOOK.md`](docs/PROMPT_BOOK.md).
