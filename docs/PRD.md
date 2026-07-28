# PRD — Final Project: Distributed Cops-and-Robbers over a Peer-to-Peer Network

**Team:** `ahk-yosi` — Yosef Shanaa (`213314859`) · Ahmad Kaiss (`325811255`)
**Course:** Orchestration of AI Agents, CS Dept., University of Haifa — Dr. Yoram Segal
**Governing document:** rules book `police_thief_p2p.pdf` **v3.0.0**. Where this PRD and the book
disagree, **the book and its binding parameter table (Appendix F) win**. This is the master PRD;
the seven stage PRDs in [`docs/PRD/`](PRD/) each define one build layer (book §10.3).

---

## 1. Vision & product statement

Two fully autonomous, **symmetric** AI agents — a **Police** and a **Thief** — chase each other on
a discrete grid over a **peer-to-peer network with no referee and no central server**. Each agent
is simultaneously a FastMCP **server** (exposing tools to the opponent) and a **client** (calling
the opponent's tools). Neither side ever sees the true world state: each maintains a **Bayesian
belief map** over the opponent's position, fused from the opponent's decaying **pheromone/scent
field** and **free natural-language hints that may lie**. Honesty is enforced not by trust but by
mathematics: every step is sealed by a **SHA-256 commit-reveal protocol** and audited mutually at
game end; any tampering is a technical loss. Matches are played in a live academic **league**
against other teams' agents over the public internet, and every valid match is auto-reported to
the lecturer via **Gmail API** as signed JSON artifacts.

The system is formally a **Dec-POMDP** ⟨n, S, {Aᵢ}, P, R, {Ωᵢ}, O, γ⟩ with n=2; the graded core is
systems engineering: coordination, adaptation under uncertainty, cryptographic integrity, and
resilient architecture — plus **our strategy** (the move policy is "the grade's core" per the book).

## 2. Goals / non-goals

**Goals**
1. A single role-configurable **peer** (`--role police|thief`) that plays a full 6-sub-game series
   against a remote opponent over a public URL with zero human intervention.
2. Full compliance with all **55 mandatory rules** (book Appendix E) and the **binding parameter
   table** (Appendix F) — §6/§7 below.
3. A **competitive strategy module** (our own brain classes) that wins on algorithmic merit at zero
   token cost by default (template banter), with optional LLM banter.
4. Complete league workflow: negotiation → constitution lock → step-0 declaration → play → mutual
   audit → result agreement → dual Gmail reports with the 4 JSON artifacts.
5. Two polished, cross-linked GitHub repos (police, thief) with academic README, PRD/PLAN/TODO,
   tagged `v1.0-submission`.

**Non-goals**
- No central referee/orchestrator process (forbidden).
- No reliance on the LLM for spatial decisions (allowed only as a negotiated mutual exception; not our default).
- No reinforcement learning requirement — RL is optional; our primary path is heuristic/search (may be added as an extension).
- Winning the league is *not* a goal of the PRD; protocol-correct, auditable, resilient play is.

## 3. Actors & environment

| Actor | Description |
|---|---|
| Police peer | Our process #1; may place barriers; wins by capture |
| Thief peer | Our process #2 (fully separate process, separate config dir, separate repo); wins by surviving |
| Opponent team's peers | Unknown implementation; only contract: MCP tools + shared constitution + book protocol |
| Lecturer | Receives Gmail JSON reports (`rmisegal+uoh26finalgame@gmail.com`); accesses repos (`rmisegal@gmail.com`); replays logs |
| LLM provider (optional) | template (default, 0 tokens) / Ollama local / `openai` / `claude_api` (small cloud model, e.g. Haiku) / `claude_cli` — keys from `.env` only, never `config/` |
| Tunnel provider | ngrok or Localtonet — public URL for league play (mandatory) |

Runtime: Python 3.13+, `uv`-managed, Windows/WSL2 dev machines; two terminals (one per peer) in
dev; two different machines in league play.

## 4. Game rules (binding, from book ch. 3–5 + Appendix F)

### 4.1 Board & coordinates
- Grid `[board size]` — **7×7 minimum** (negotiable upward only, e.g. 10×10).
- Cell = `(row, col)`; origin corner **top-left**, index starts at **0** (both negotiable, must be identical for both peers).
- Start positions negotiable; default example: thief center `(3,3)`, cop corner `(0,0)`.

### 4.2 Movement
- Per turn exactly one of: **N/S/E/W one cell, or STAY**. **No diagonals** — an attempted diagonal
  is rejected by the *opponent* (each side enforces physics) and costs the game.
- Turn order and sync are governed by the state machine (§5.4); a "full turn" = both agents moved
  (scent decay ticks after each full turn).
- **First mover:** the book does not fix which role moves first — it is agreed at handshake.
  Our default proposal: **thief moves first** (classic pursuit convention). Recorded in the
  interpretation log (§5.7) as an academic-freedom decision.

### 4.3 Barriers (police only)
- In a turn where the police **forgoes movement**, it may place one barrier on its own cell or one
  of the 4 orthogonally adjacent cells. Quota: `[barrier quota]` = **14 (min)**.
- A barrier is permanent and impassable **to both** players.
- Placing a barrier on the thief's current cell **captures the thief**; a thief left with no legal
  move (walls/barriers on all sides) is also captured.
- **Every placement must be truthfully declared with its exact location** — hidden or misreported
  barriers are a disqualification (#15–16).

### 4.4 Win conditions & scoring (per sub-game)
| Event | Condition | Police | Thief |
|---|---|---|---|
| Capture | Police lands on thief's cell and issues a Capture Claim (thief is cryptographically obliged to answer truthfully); or barrier-capture / enclosure | **20** | 5 |
| Survival | Thief survives `[survival threshold]` = **35 (min)** valid steps uncaptured (step cap `[move cap]` = **35 (min)**) | 5 | **10** |
| Technical loss | Crash, timeout, or crypto forgery by a side | 0 | 0 |
| Series tie | Aggregate score of all sub-games equal | **2** | **2** |

- Series vs one opponent = `[number of sub-games]` = **6** (fixed).

### 4.5 Scent / pheromone model (fixed parameters)
- Each move/stay emits a **5×5** field centered on the agent: center intensity **0.9**, radial falloff.
- After each full turn every cell decays: `τ(t+1) = max(0, (1−ρ)·τ(t) + Δτ)`, **ρ = 0.10**;
  cell values are continuous in **[0, 0.9]** (never negative, never above the focal intensity).
- Each side reads **only the opponent's** scent field; scent is natural and unforgeable — the only
  deception channel is the verbal hint.
- **Before a series, both teams must exchange the emission+decay model with a concrete numeric
  example and lock it cryptographically (SHA-256)**; sharing our scent-engine code with the
  opponent is allowed and recommended.

### 4.6 Verbal hints
- Free natural language only (**mandatory**); direct numeric-coordinate protocols are forbidden (#26–27).
- Max `[hint word limit]` = **15 words** (negotiable); applies to template and LLM output alike.
- May be true or false; the **Intent flag (truth/lie) is inside the commit**, so a lie is always
  premeditated and provable at audit — this is legal deception.
- Optional `[map area]` (e.g. "New York") seeds hints with real landmarks; empty ⇒ generic landmarks.

### 4.7 Commit-reveal protocol (every step, both sides)
1. **Commit** — send `H = SHA256(canonical_json({state, move, intent, nonce, hint, verdict, step, role, sub_game}))`; nonce from `secrets` (16 bytes hex), fresh per commit.
2. **Acknowledge** — opponent confirms it is locked on our commit.
3. **Reveal** — send move + hint (+ intent/verdict); **nonce stays secret**.
4. **Final Audit** (end of game) — all nonces revealed; each side re-hashes the opponent's entire
   log; any single mismatch ⇒ `TAMPERED` ⇒ technical loss, no appeal.
- Capture Claims and win claims ride this protocol; a false answer is caught at audit.

### 4.8 Step-0 (pre-game) declaration — mandatory
The `[declaration file]` (`declaration_<game_id>.json`) fixes, cryptographically signed,
**everything constant for the whole match** (all sub-games):
- **Both teams' identities and members** (names + IDs);
- **All four repo URLs** (each team's police + thief repos) and **both MCP server addresses**;
- Hardware spec per side: OS, CPU cores/frequency, RAM, GPU/VRAM;
- LLM model name, the **agreed token cap** for the series;
- **Code version**, **game number**, and the **git commit hash actually being played** (code may
  change between matches; each match's commit must be declared, #53 — and it also appears as the
  `github_commit` field in the emailed result JSON);
- Game **start and end times**.
LLM token consumption is metered and sealed during play and reported in the result file (#54).

## 5. System requirements

### 5.1 Architecture (mandatory patterns)
- **Two fully separate processes** for police and thief; separate config dirs `/config/police` vs
  `/config/thief`; **no shared memory/variables/live-state modules** (#1–2).
- **Orchestrator pattern** inside each peer: a single gateway coordinating MCP connector, decision
  module, log manager, deadline tracker, watchdog (#3).
- **State machine** (mandatory, #4–5): `WAITING_FOR_OPPONENT → COMPUTING_MOVE → COMMITTING →
  AWAITING_REVEAL → VERIFYING → (loop)`; error transitions to terminal `TECHNICAL_LOSS`; illegal
  transitions raise immediately.
- **Three distinct timers** (do not conflate): `response_timeout_sec` — per MCP request
  (30 s default, shared JSON, negotiable; deadline tracker retries then technical loss, #6);
  `watchdog_timeout_sec` — whole-system heartbeat freeze threshold (60 s default, shared JSON;
  watchdog persists state + controlled shutdown, #7); `turn_timeout_seconds` — maximum wait for
  the opponent's *turn* (180 s default, private TOML; a silent opponent past it is a technical loss).
- **Strategy module is a separate, pluggable component** hooked into the PeerRuntime between hint
  decode and commit pack; selected in private TOML `[strategy]` (`police_class` / `thief_class`,
  `package.module:Class` subclassing `BrainBase`).

### 5.2 Configuration contract
- **Shared constitution** `config/game.json` — everything both sides must agree on: board, starts,
  axis convention, move set, barrier quota, move cap, survival threshold, scoring, pheromone
  params, map area, hint word limit, network/league params, rate-limiter params. Canonical JSON
  (sorted keys, fixed separators), **byte-identical on both sides**, SHA-256-locked pre-game;
  a per-match copy is named uniquely and **committed to the repo** (Appendix F mandatory rules).
- **Private per-peer** `config/game.toml` — group identity, members, repo URLs, my port, opponent
  URL, turn timeout, `[strategy]`, `[trash_talk] provider`, `[llm]` model + step deadline,
  `[email]` recipient/mode. Never crosses the network; shared JSON **overrides** any overlapping key.
- Parameter statuses: **fixed** (never change), **minimum** (raise only by mutual agreement),
  **negotiable** (any mutually agreed value); defaults = the book's example values.

### 5.3 Networking
- FastMCP server per peer (`http`, bind `0.0.0.0`); dev on localhost (thief 8801 / police 8802
  convention), league play through **ngrok/Localtonet public URLs** (#10).
- Tolerate opponent restarts/latency: connect-retry until the opponent's server is up; timeouts
  never hang (deadline tracker).

### 5.4 GUI & replay (mandatory deliverables)
- **Live GUI** (Tkinter) per peer showing **Local Truth only**: own position/quota, opponent's
  scent field, **belief heatmap** (red intensity = P(opponent here)), and a **turn banner** (green
  `YOUR TURN` / gray `LOCKED` after commit; input locked out of turn). Showing the objective board
  is a violation (#8–9). Headless mode (`--no-gui`) for automation.
- **Replay Viewer**: loads `[log file]`, step forward/back, re-computes every commitment hash live,
  green **`Verified OK`** stamp / red **`TAMPERED`** banner (match void). Submission requires
  screenshots of both the belief heatmap and `Verified OK`.

### 5.5 Reporting & league automation
- After every valid match: **both teams agree on the result, and each team independently emails**
  a machine-readable **JSON attachment** (plaintext body reports are rejected) to
  `[agent report address]` = `rmisegal+uoh26finalgame@gmail.com` (#32–35). No report from a side ⇒
  that side gets no points.
- **Four artifacts** per game, common `game_uid`:
  `declaration_<game_id>.json`, `config_<game_id>_g<NN>.json`, `log_<game_id>_g<NN>.json`
  (step-by-step sealed records **including the hints and the LLM-discussion fields**, nonces and
  hashes — the replay viewer's input), `result_<game_id>.json`. The result includes both teams'
  repo links (4 links), the per-sub-game commit hash (`github_commit` field), and total tokens
  consumed.
- **Gatekeeper** in front of Gmail (mandatory): Quota Manager (daily cap), **Token-Bucket rate
  limiter** (`tokens ← min(C, tokens + r·Δt)`, allow iff ≥1; ≥30 req/min, ≥2 concurrent, ≥5 s
  backoff, ≥3 retries, ≥100 queue), **DOS detector** (anomaly ⇒ hard lock). Respect HTTP 429 with
  backoff (#28–29).
- OAuth 2.0 with **`gmail.send` scope only** (#30); `credentials.json`/`token.json` git-ignored
  forever (#39–40).
- League rules: declare prior counted-game count before each match (#37–38, truthfully); **one
  counted game per opponent** (#52); warm-ups unlimited/uncounted; **≥2 counted matches vs
  different teams to pass** (fixed), **≤10 counted total** (fixed); diversity reward 10 (fixed);
  computational fairness — efficiency is rewarded in grading, brute force is not.

### 5.6 Engineering quality (course "recommendations" file + reference repo bar)
- `uv` only; Ruff clean; pytest with coverage ≥85%; every source/test file ≤ ~150 code lines;
  TDD; English-only code comments; small single-purpose modules; CI on both repos.
- All tunables from config — nothing hard-coded; deterministic seeds where possible; JSONL/JSON
  logs enable full deterministic replay.

### 5.7 Interpretation & contradiction handling (academic freedom)
The book grants explicit academic freedom on internal contradictions: where two passages dictate
different behavior we may choose either — **provided the report documents where the contradiction
was found, what we chose, and why** (quantitative values always defer to the Appendix F table).
We maintain an **interpretation log** section in each repo's README (canonical location) covering
every such decision. Current entries: (1) per-step Reveal discloses the public projection only —
moves/positions/nonces open at the sub-game audit (fig. 6 read literally would collapse partial
observability; matches the reference implementation); (2) first mover = thief (§4.2); (3)
capture-claim query semantics — only the thief's sealed truthful answer constitutes capture, and
the claim rides inside the reveal (§4.4/#21–22); (4) scent served pre-emission (freshest visible
τ≈0.81, the book's own worked example); (5) τ clamped to [0,0.9], decay applied per own-step
(audit-reproducible, equivalent under strict alternation). Legal-loophole exploitation and rule
upgrades by mutual agreement are explicitly encouraged by the book — any such agreement is
recorded in the per-match config + interpretation log.

## 6. Mandatory-rules compliance map (Appendix E digest — all 55)

| # | Rule (digest) | Owning stage PRD |
|---|---|---|
| 1–2 | Separate processes; zero shared state | PRD-2 |
| 3–5 | Orchestrator gateway; strict state machine; reject illegal transitions | PRD-2 |
| 6–7 | Deadline tracker; watchdog with controlled shutdown | PRD-2 |
| 8–9 | Local-truth GUI; never show objective board | PRD-7 |
| 10 | Tunnel to public internet | PRD-5 |
| 11–12 | Byte-identical config; raise minimums only | PRD-1/PRD-5 |
| 13–14 | Orthogonal moves only; no diagonals | PRD-1 |
| 15–16 | Declare barrier placements truthfully | PRD-1/PRD-6 |
| 17–19 | SHA-256 commit-reveal; nonce secrecy until audit; hash mismatch ⇒ technical forfeit | PRD-6 |
| 20 | Replay viewer for log verification | PRD-7 |
| 21–22 | Truthful capture answers; false capture claim ⇒ disqualification | PRD-6 |
| 23 | Lock scent model cryptographically pre-game | PRD-4/PRD-6 |
| 24 | Signed step-0 hardware declaration | PRD-6 |
| 25 | LLM never decides moves (recommendation; hallucination risk) | PRD-3 |
| 26–27 | Free natural-language dialogue; no numeric-coordinate protocol | PRD-4 |
| 28–30 | Token-bucket limiter; DOS detector; `gmail.send` scope only | PRD-7 |
| 31–38 | League minimums, auto-report, JSON attachment, result agreement + dual reports, mutual audit, truthful game-count declaration | PRD-7 |
| 39–41 | No secrets in repos; `.gitignore`; annotated submission tag | PRD-7 / submission |
| 42–45 | Academic README; Moodle PDF form; per-member submission; 8-char group code | submission |
| 46–48 | Barrier-capture; enclosure-capture; score every ending per table | PRD-1 |
| 49–51 | Two repos + cross-links + 4 links in report; repo must contain README/config/PRD/PLAN/TODO; reports to lecturer address | PRD-7 / submission |
| 52–55 | One counted game per opponent; per-match commit hash; report token totals; self-grade = code quality only | PRD-6/PRD-7 / submission |

## 7. Binding parameters (Appendix F — single source of truth)

| Parameter | Default | Status |
|---|---|---|
| Board size | 7×7 | minimum |
| Number of agents | 2 | fixed |
| Axis origin / start index | top-left / 0 | negotiable |
| Thief / Police start | (3,3) / (0,0) | negotiable |
| Map area | "New York" | negotiable |
| Hint word limit | 15 | negotiable |
| Move set | N,S,E,W,STAY | fixed |
| Barrier quota | 14 | minimum |
| Move cap / survival threshold | 35 / 35 | minimum |
| Scent: center τ / decay ρ / field | 0.9 / 0.10 / 5×5 | fixed |
| Scoring: capture 20/5, survival 5/10, tie 2, technical 0 | — | fixed |
| Sub-games per series | 6 | fixed |
| Diversity reward | 10 | fixed |
| Min counted matches to pass / max per team | 2 / 10 | fixed |
| Token budget per series | ~200,000 | negotiable |
| Rate limiter: 30 rpm / 2 conc / 5 s backoff / 3 retries / 100 queue | — | minimums |
| Response timeout / watchdog | 30 s / 60 s | negotiable |

## 8. Strategy & tactics (the graded core — our interpretation)

> Detailed design in [`PLAN.md`](PLAN.md) §6 and PRD-3/PRD-4. Move choice is **always pure Python**.

- **Belief engine (both roles):** grid posterior from scent likelihood (emission×decay forward
  model) × hint likelihood × motion model; a **trust coefficient** per opponent, updated whenever
  a hint contradicts unforgeable scent evidence (the book's "moved north but scent is SE" test).
- **Police:** minimize Manhattan distance to belief argmax, tie-broken by expected entropy
  reduction (information-gain patrol); barrier play = corridor building & pocket sealing with a
  connectivity check (never self-trap, quota-budgeted endgame sealing); barrier-capture when
  belief mass on an adjacent cell is near-certain; deceptive hints to herd the thief toward traps.
- **Thief:** maximize expected distance from the belief cloud over the police, weighted by
  mobility (count of open escape routes — corner avoidance); plan around truthfully-declared
  barriers; **scent-aware pathing** (avoid re-emission hotspots, move away from own scent
  centroid); **scent-consistent lying** — generate hints that match our *stale* trail so the
  opponent's contradiction detector stays quiet.
- **Excellence extensions (candidates):** particle-filter belief tracker with opponent motion
  model; Beta-distribution hint-trust learner; bounded expectimax over belief states;
  articulation-point analysis for barrier safety; auto-negotiation advisor; post-game analytics
  notebook (token/cost/win-rate studies, as in the reference `RESEARCH-REPORT`).

## 9. Acceptance criteria (product level)

1. `uv run python -m <pkg> peer --role police` + `--role thief` on two machines over public URLs
   complete a full 6-sub-game series unattended, produce the four artifacts, and both GUIs show
   belief heatmaps + turn banners with no ground-truth leak.
2. Replay of every produced log shows `Verified OK`; a deliberately corrupted log shows `TAMPERED`.
3. Kill-tests: opponent silent past timeout ⇒ clean technical-loss path; watchdog fires on frozen
   loop ⇒ state persisted, controlled shutdown.
4. Gmail report sent by our side automatically, JSON attachment validating against our schema;
   token-bucket provably blocks a synthetic burst; DOS detector locks a synthetic loop.
5. Both repos pass CI (Ruff clean, coverage ≥85%), contain README(5 components)+PRD+PLAN+TODO+
   per-match configs, cross-links, tag `v1.0-submission`, zero secrets in history.
6. ≥2 counted league matches vs different teams played and reported (both sides), plus warm-ups.
7. Evidence explicitly mapped to the book's **four success metrics** — Coordination (P2P turn
   management, ch.2), Adaptation (belief under uncertainty, ch.4+6), Integrity (commit-reveal +
   audit, ch.5), Architecture (Gatekeeper/Orchestrator resilience, ch.8+10) — in the README.

## 10. Open decisions & external inputs

| Item | Status |
|---|---|
| Package/repo names (two repos) | proposed: `p2p-police-agent` / `p2p-thief-agent` |
| 8-char group submission code | to be chosen (no spaces) |
| Partner teams for league matches (≥2) | to coordinate in class |
| Tunnel provider (ngrok vs Localtonet) + account | to decide in PRD-5 |
| Banter provider default | `template` (0 tokens); optional `ollama` if installed |
| Negotiation defaults we will propose | 7×7, book defaults, map area "New York" |
| Build-fresh vs fork decision | **build fresh, reuse HW6 assets** — see PLAN ADR-1 |
