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
        A_ENG --> A_BR[PoliceBrain\ntuned doctrine]
        A_ENG --> A_BEL[Belief map + trust]
        A_RT --> A_GK[Gatekeeper] --> A_MAIL[Gmail reporter]
    end
    subgraph PeerB["Thief peer (port 8801)"]
        B_ENG[TurnEngine] --> B_BR[ThiefBrain\ntuned doctrine]
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

**Police — interception, then the squeeze.** The freshest scent cell marks where the thief *was*;
consecutive freshest cells yield a velocity estimate, and the brain solves a small pursuit curve
to step toward where the thief *will be* (lookahead k ∈ 0..4). Every threshold is a **ratio of a
rolling window of recent belief peaks**, never an absolute — v3's kill shot needed 0.30 while the
measured peak never exceeded 0.294 over 385 turns, so it was unreachable dead code. Ambush the
argmax for exactly one turn (a second is the camping pathology that idled 21% of all turns), and
break ties against reversing (28% of real moves were A→B→A step-backs). Once the gap stops
closing, switch from chasing to the book's third capture path (§3.4): **close the evader's exits
one at a time** — enclosure costs two barriers in a corner, where landing on a moving equal-speed
evader is near-impossible. Flood-fill vetoes self-trapping placements, and an enclosed opponent
is *claimed*, because a foreign peer will never confess it (that fix alone turned 0/5 into 5/5
against the live reference peer).

**Thief — risk-aware evasion off the pursuer's trail.** Candidate cells are scored by the
police's *projected* belief mass within claim range (BFS ≤ 2), fleeing the pursuer's **scent
trail** rather than our posterior of it (measured: our belief of the police sits 1.85 cells off,
so fleeing the posterior means fleeing a phantom). Two-ply mobility, forward-projected
interception risk, juking only under genuine close pursuit, corner discipline scaled by the
pursuer's *remaining* barrier quota, never STAY twice, and **scent-consistent lies** sampled with
a private RNG — the old lie picked the furthest stale cell of a field we transmit ourselves,
making it a deterministic function of public data.

**Evidence.** Validation seeds unseen by both the search and its hold-out, scored in league points
against a population of opponent archetypes (not self-play — see §4): **12.35 → 13.00
points/sub-game, capture 75.0% → 79.8%, survival 80.0% → 92.0%**. Live against the reference implementation: police 5/5 captures, thief
never caught. Full tuning history, including the negative results that cost real effort and the
two hand-measured verdicts the search overturned: [`docs/STRATEGY.md`](docs/STRATEGY.md).

## 4. Reinforcement learning

**Used, offline, in the policy-search family — and deliberately never during a match.**
Package: [`src/p2p_pursuit/learn/`](src/p2p_pursuit/learn/). Method: the cross-entropy method
over the doctrine vector, plus behaviour cloning of real opponents from sealed match logs.

**Why not online.** The league grants at most ten counted games, one per opponent, each sealed
after reporting. That is ten terminal rewards against ten different non-stationary opponents —
far too few to fit anything, and every sample is irreversible. Worse, a policy that updates
mid-league means the version that earned game 3 is not the version playing game 7, which the
per-sub-game `github_commit` in the report is supposed to pin down. So the agent that plays a
counted match is **frozen**: `config/doctrine.json`, committed, reproducible from the hash.

**What is learned.** Every constant either brain reads is a field of
[`strategy/params.py`](src/p2p_pursuit/strategy/params.py) (23 dimensions), and CEM samples
policies, keeps the elite quarter, and refits the sampling distribution. Three properties make
it honest on a noisy objective, and each is asserted by a test: **common random numbers** (every
candidate in a generation is judged on the same seeds, so comparing them is not comparing luck),
**elitism** (the incumbent is re-scored every generation and competes), and a **variance floor**
(without it the distribution collapses into the first plausible basin and stops searching). The
objective is *league points per sub-game*, not capture rate — the table pays 20/5 as police and
5/10 as thief, so a doctrine can win the capture metric and lose the league.

**Why the opponent pool is the real contribution.** Self-play here is a measured liar: the v5
police scored 90–98% against our own thief and **0/5** against the live reference peer, because a
simulation containing one evader teaches you about that evader. Candidates are therefore scored
against a population of archetypes — random walker, momentum runner, distance-gradient chaser and
fleer, trail hound, barrier-spender, mobility-preserving holder, and ourselves — each declaring
*which roles it is genuinely distinct in*, because listing an archetype in a role where it plays
an identical trajectory would silently triple that behaviour's weight in the objective.

**Learning between matches (the part that compounds).** After the audit exchange, a sealed log
holds the opponent's exact position and move at every step — the protocol hands us a labelled
dataset of a real team. `learn clone` fits a linear policy to it and adds that team to the pool,
so the next search answers opponents that are no longer hypothetical:

```bash
uv run p2p-pursuit learn clone --match matches/<team>            # their moves -> a playable policy
uv run p2p-pursuit learn tune  --role police --workers 12        # search, hold-out gated
```

`tune` writes `config/doctrine.json` **only if a hold-out seed set the search never saw
improves** — a gain on the training seeds is the optimizer reporting its own noise back.

Two things are still not RL and are not claimed as such: the per-turn move remains deterministic,
auditable Python over an exact Bayes filter (rule #25 — the LLM only ever writes banter), and the
sub-game trust coefficient adapts online by Bayesian update, not by reward.

## 5. Screenshots

*(Mandatory evidence. The first three were captured live on this codebase — a real two-peer
match over localhost MCP and the replay/tamper drill; the league terminal shot lands during
the first counted match.)*

### Live GUI — Bayesian belief heatmap (local truth only)

![Live belief field: the police peer's posterior mid-match](docs/img/live_belief_heatmap.png)

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
| 5. Cloud exposure — public-URL config, smoke probe, [`docs/RUNBOOK.md`](docs/RUNBOOK.md), CI chaos drills (latency / dead link / silence) | ✅ incl. live two-tunnel drill + tunnel-kill drill |
| 6. Crypto — commit-reveal, nonces, mutual audit, step-0 declaration, locks | ✅ |
| 7. Reporting + GUI — 4 JSON artifacts, Gatekeeper, Gmail (draft/send), live GUI, replay verifier | ✅ |
| 8. Interop — dialect detection, reference-dialect bridge, cross-dialect audit | ✅ proven vs. the unmodified reference peer |
| 9. Offline learning — CEM policy search over the doctrine vector, opponent cloning from sealed logs | ✅ frozen into `config/doctrine.json`; never runs during a match |

**Quality gate:** 213 tests, coverage 93% (gate 85%), Ruff clean (E/F/W/I/N/UP/B/C4/SIM),
CI on every push. Counted league matches vs. real opposing teams
are the remaining work (see [`docs/TODO.md`](docs/TODO.md) §8–9); the submission repos are
already split, public and green.

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

# Probe a (remote) peer: reachability + which wire dialect they speak:
uv run p2p-pursuit smoke http://127.0.0.1:8801/mcp     # dialect=native|reference|unknown

# One-time Gmail consent:
uv run p2p-pursuit authorize

# --- offline only; never during a match (see 4) -------------------------------
# Fit a policy to a team we have played, from their sealed logs, and pool it:
uv run p2p-pursuit learn clone --match matches/<archived-dir> --name <team>

# Search the doctrine vector; writes config/doctrine.json only if a hold-out improves:
uv run p2p-pursuit learn tune --role police --generations 20 --seeds 40 --workers 12
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
  strategy/   police_brain, thief_brain, params (the tunable doctrine vector),
              pathing, squeeze, talk_template, talk_llm
  learn/      OFFLINE ONLY - cem (policy search), arena (points objective),
              population + opponents (sparring archetypes), clone_data + clone_fit
              (fit a real opponent from its sealed logs)
  peer/       engine_state, turn_engine, service, runtime(+reports), local_match,
              state_machine, deadline, watchdog, log_manager, audit_bridge
  infra/      mcp_server, mcp_client, transport, email_sender
  report/     artifacts (declaration/config/log/result), results
  gui/        live_view (belief heatmap + banner), replay_view, replay_data, view_model
  shared/     config (JSON constitution + private TOML), gatekeeper, rate_limiter, sysinfo
config/police/  config/thief/   # byte-identical game.json + role-private game.toml
config/doctrine.json            # the frozen tuned doctrine a counted match plays
config/opponents/               # policies cloned from teams we have already played
matches/     # tracked per-match artifact archive (configs, logs, results)
tests/unit/  tests/integration/ # 89 tests incl. real MCP round-trip + cheat harness
docs/        PRD, PRD/1..7, PLAN, TODO, STRATEGY, GAP_ANALYSIS, RUNBOOK, PROMPT_BOOK, COST_ANALYSIS
```

## 12. Documentation map

| Doc | What |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) + [`docs/PRD/`](docs/PRD/) | Master requirements, 55-rule map, binding parameters, seven stage PRDs |
| [`docs/PLAN.md`](docs/PLAN.md) | Architecture, mermaid diagrams, ADRs, reuse map, milestones, risks |
| [`docs/STRATEGY.md`](docs/STRATEGY.md) | The graded core: doctrine + evaluation numbers, including the offline policy search (§8) and every negative result it overturned |
| [`docs/TODO.md`](docs/TODO.md) | Task tracking with milestone gates |
| [`docs/GAP_ANALYSIS.md`](docs/GAP_ANALYSIS.md) | HW6 vs. final-project spec |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Tunnel + league match operations, interop with reference-derived peers, **and the between-match learning loop (§4b)** |
| [`docs/PROMPT_BOOK.md`](docs/PROMPT_BOOK.md) | Prompt-engineering log (guidelines §8.3) |
| [`docs/COST_ANALYSIS.md`](docs/COST_ANALYSIS.md) | LLM token/cost model per banter provider |
| [`docs/SUBMISSION_CHECKLIST.md`](docs/SUBMISSION_CHECKLIST.md) | The book's ch. 11.5/11.6 final sweep, mapped to evidence |
| [`matches/`](matches/) | Per-match archives (artifacts, configs, terminal evidence) |

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

7. **The commit *formula* is a negotiable term, not a constant.** The book fixes what must be
   sealed, not how the digest is composed, and two honest implementations diverged: ours hashes
   the record with the nonce inside it, the reference hashes `canonical(payload)|nonce`. Neither
   can verify the other, so `[interop] dialect` selects the composition per match (default
   `native`; every log records which one sealed it). Adopting the opponent's composition changes
   nothing about *what* is committed to or how binding it is — a nonce is still withheld until
   the audit, and tamper sensitivity is unit-tested under both. Proven against the unmodified
   reference peer: `matches/warmup-reference-interop/`.
8. **An opponent's unsealed assertions are acted on but recorded as unsealed.** The reference
   protocol carries the thief's capture answer and the survival claim as plain fields outside
   its commitment, where ours binds both (rule #21). Refusing them would hang the match, so they
   are applied with `(unsealed claim)` / `(unsealed answer)` in the cause string, which then
   travels into the log, the result and the replay. Relatedly, our result reports
   `mutual_agreement: false` for a reference-dialect match: that dialect never returns the
   opponent's verdict of us, and asserting an agreement we never received would be a lie in a
   signed artifact.

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
