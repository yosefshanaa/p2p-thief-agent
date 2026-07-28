# Gap Analysis — HW6 ("Cop & Thief via MCP") vs. Final Project ("Distributed Cops-and-Robbers over P2P")

> Sources: final-project rules book `police_thief_p2p.pdf` **v3.0.0** (Dr. Yoram Segal, 2026),
> reference repo [`rmisegal/Game-P2P-Cop-Chase`](https://github.com/rmisegal/Game-P2P-Cop-Chase) **v3.0.0**,
> and our working HW6 repo (`/mnt/c/Orch/HW6`, team `ahk-yosi`).

## 1. Executive summary

HW6 is a **working, battle-tested system** (174 tests, CI, live Cloud Run deployment, a real
cross-team match played and reported). But the final project is **not "HW6 with more features"** —
it changes the trust model, the physics, and the observability model at the root:

| Axis | HW6 | Final Project | Verdict |
|---|---|---|---|
| Trust model | **Central orchestrator + single authoritative referee** validates every move | **No referee at all.** Two symmetric peers; truth is built bottom-up via **SHA-256 commit-reveal** + mutual post-game audit | **Rebuild** — the architectural core is different |
| Topology | Orchestrator (MCP *client*) drives two agent-side MCP *servers* | **True P2P**: each agent is *simultaneously* an MCP **server and client** (`PeerRuntime`) | **Rebuild** |
| Board | 5×5, start distance 3 | **7×7 minimum** (negotiable upward, e.g. 10×10), thief starts center `(3,3)`, cop corner `(0,0)` (negotiable) | Adapt (config-driven in both) |
| Movement | **8-directional** (king moves) | **4-orthogonal + STAY only; diagonals are an infraction** (opponent rejects them → loss) | **Change engine rules** |
| Barriers | Cop places ≤5, tactical adjacent-cell rule, stepping into one loses | Cop **forgoes movement** to place a barrier on his own cell or a 4-adjacent cell; quota **14 (min)**; barrier onto thief's cell = **capture**; enclosed thief = captured; **placement must be truthfully declared** | **Change engine rules** |
| Observability | Chebyshev **vision radius** (r1/r2 fog) | **No vision at all.** Each side senses only the opponent's **pheromone/scent field** (5×5 emission, center τ=0.9, decay ρ=0.10) + free-text hints that may lie → **Bayesian belief map** | **New subsystem** (scent + belief) |
| Deception channel | Free-text `message`, referee ignores it | Free-text hint (≤15 words) with a committed **Intent flag (truth/lie)**; scent cannot lie; barrier & capture claims **must** be truthful | New protocol semantics |
| Integrity | Referee is the truth; bearer-token auth | **Commit → Acknowledge → Reveal → Final Audit** on every step; canonical-JSON SHA-256; nonces (from `secrets`) revealed only at audit; any mismatch = `TAMPERED` → technical loss (0/0) | **New subsystem** (crypto) |
| Fairness | — | **Step-0 signed hardware + code-version + commit-hash declaration**; LLM token consumption metered and sealed; league normalization rewards efficient algorithms | **New subsystem** |
| Scoring | Cop win 20/5, Thief win 5/10, 6 sub-games | Capture **20/5**, Survival(35 steps) **5/10**, Technical loss **0/0**, **tie = 2 each**; series of **6 sub-games** per opponent | Adapt (values differ, tie rule new) |
| Networking | HTTPS Cloud Run + bearer token | **Tunneling (ngrok / Localtonet) is mandatory** for league play; localhost only during development | Adapt (our deploy skills transfer; tunnel replaces Cloud Run as the required minimum) |
| Config | `config.yaml` (ours only) | **Shared signed constitution** `config/game.json` (canonical JSON, byte-identical, SHA-256-locked, negotiated per match) + **private** `config/game.toml` per peer | **New contract** |
| LLM role | LLM/search agents chose moves | **Move decision must be pure algorithm** (LLM-move only by explicit mutual agreement); LLM only writes the bluff, in 4 modes (`template`/`ollama`/`claude_api`/`claude_cli`), budget ≈200k tokens/series | Adapt (our "search picks move, LLM writes bluff" split already matches the spirit) |
| GUI | Web GUI **with a truth board** | Live GUI must show **Local Truth only** — belief heatmap + turn banner; **showing the objective full board is a disqualifiable violation**. Separate **Replay Viewer** re-verifies every hash (`Verified OK` / `TAMPERED`) — a **mandatory** deliverable | **Rebuild GUI**; replay-verification is new |
| Reporting | §9.1/§9.2 JSON via Gmail (OAuth, mockable) | **Four standardized JSON artifacts** per game (`declaration_`, `config_`, `log_`, `result_`), JSON **attachment** (plaintext rejected), both teams send separately to `rmisegal+uoh26finalgame@gmail.com`, Gatekeeper (quota + token-bucket + DOS detector) required | **Reuse & extend** (our Gmail + Gatekeeper code is a strong base) |
| League | One bonus match | Real league: ≥**2** counted matches vs different teams to pass, ≤**10** counted, **one counted game per opponent**, warm-ups free, diversity reward 10, game-count declaration, both-sides agreement | New process |
| Submission | One repo | **Two separate repos (police, thief)**, cross-linked READMEs, annotated tag `v1.0-submission`, academic README (5 mandatory components), **PRD/PLAN/TODO files are mandatory repo content**, per-match config committed, Moodle PDF per member, 8-char group code, self-grade for code quality only | New process |

## 2. What carries over from HW6 (assets)

**Direct reuse (small adaptation):**
- `shared/gatekeeper.py` — API Gatekeeper (rate limits, retries, logging) → base for the mandatory Gatekeeper (add token-bucket + DOS detector + quota manager per book §9.3).
- `reporting/gmail_reporter.py` + OAuth flow — real, proven `gmail.send`-scoped sender with mockable tests → adapt payload to the 4-artifact format and JSON-attachment rule.
- `shared/config.py` patterns — schema-validated config loading → extend to the JSON(shared)/TOML(private) dual contract with canonical serialization + `config_sha256`.
- Engineering discipline: uv, Ruff, pytest ≥85% coverage, ≤150-line modules, CI workflows, TDD — all directly demanded by the course's "recommendations" file and matching the reference repo.
- Ops experience: token exchange, smoke tests, partner-team coordination protocol (`SHARED_MATCH_RULES.md` playbook style), YouTube/photo evidence discipline.

**Reuse as design knowledge (rewrite the code):**
- Strategy layer: our minimax-over-real-rules + "LLM writes only the bluff" split is exactly the final project's required philosophy; the search core must be rewritten for 4-orthogonal moves, barrier-as-turn-action, and **belief-state** (no ground-truth opponent position!).
- JSONL step logging + deterministic replay: concept carries; format changes to the book's sealed log (`log_<game_id>_g<NN>.json`) with commit/nonce fields.
- State-machine turn loop, technical-loss handling, safe-move fallback.

**Not reusable:**
- The referee/orchestrator as ground truth (violates the P2P zero-trust model).
- Vision-radius observation service (replaced by scent+belief).
- 8-direction movement engine, HW6 scoring table values, single-repo layout, web truth-board GUI.

## 3. What is brand-new (must be built from zero)

1. **PeerRuntime** — one autonomous peer = FastMCP server + client + negotiation + turn loop.
2. **Commit-reveal cryptography** (canonical JSON, nonce lifecycle, mutual audit, tamper forfeit).
3. **Scent/pheromone engine** (emission field, decay law, symmetric read of the opponent's field) + **cryptographic lock of the formula (with a numeric example) before the series**.
4. **Bayesian belief map** fusing scent evidence with hint text and a trust coefficient.
5. **Pre-game negotiation & constitution signing** (parameter deal, byte-identical `game.json`, hash exchange, per-match config files, commit-hash declaration).
6. **Step-0 declaration** (hardware, code version, git commit, token budget) — signed.
7. **Local-truth Tkinter live GUI** (belief heatmap + turn banner) and the **hash-verifying Replay Viewer**.
8. **League workflow automation** (game-count declaration, result agreement, dual independent Gmail reports, four artifacts).
9. **Two-repo delivery pipeline** with cross-links and per-match config archiving.

## 4. Relationship to the reference repo (`Game-P2P-Cop-Chase` v3.0.0)

The lecturer's repo already implements the mechanics end-to-end (peers, commit-reveal, scent,
belief, negotiation, GUI+replay, 4 artifacts, Gatekeeper, email) but **deliberately ships a
trivial strategy** — the book states it is a *learning aid, not a submission skeleton*, and where
it deviates, *the book + binding parameter table win*. Our policy (recorded in PLAN ADR-1):

- Use it to **learn interfaces** (`BrainBase`, `[strategy]`/`[trash_talk]` extension points, artifact schemas).
- **Do not fork it as our skeleton.** We build our own codebase to the same contract, importing our
  HW6 engineering assets, so the graded work (architecture + PRD-driven prompts + strategy) is ours.
- Keep wire-compatibility in mind: opponents may run reference-derived peers, so our MCP tool
  names/payloads and artifact schemas must interoperate (verify in warm-up games).

## 5. Grading-critical deltas (do not miss)

- **PRD/PLAN/TODO files in each repo are mandatory content** (book §9.4 + rule #50) — this very
  documentation set is part of the submission, and the prompts we feed our AI coding agents are graded.
- **Free natural-language dialogue is mandatory**; a numeric-coordinates hint protocol is an infraction (#26–27).
- **Live GUI must never show the true board** (#8–9) — HW6's truth board would disqualify here.
- **Replay Viewer with hash verification is a submission gate** (#20), with screenshots (`Verified OK`, belief heatmap).
- **Both teams report separately; a missing/contradicting report voids the match score** (#35).
- **Never lie about capture / barrier / game-count declarations** (#16, #21–22, #38) — the only legal lie is the hint text.
- **Secrets never enter any repo** (#39–40), even private ones.
- **Self-grade reflects code quality only, not match results** (#55).
