# CONTINUATION PROMPT — finish the P2P Cops-and-Thieves final project

*Paste everything below this line into a fresh Claude Code session started in
`/mnt/c/Orch/final_Project` to continue exactly where the project stands.*

---

You are continuing the final project for Dr. Yoram Segal's **"Orchestration of AI Agents"**
course (University of Haifa): a distributed cops-and-robbers game between two autonomous AI
peers over FastMCP — true P2P, **no referee**, every step sealed with SHA-256
commit → acknowledge → reveal → mutual audit (tamper ⇒ technical loss 0/0).
Team `ahk-yosi`: Yosef Shanaa (213314859) + Ahmad Kaiss (325811255).

## Current state — the code is DONE and green

- Workspace/monorepo: `/mnt/c/Orch/final_Project` → https://github.com/yosefshanaa/final_Project
  (branch `master`, gh account `yosefshanaa`, gh CLI authenticated). All seven build stages of
  the book's §10.3 are implemented and gated: 89 tests, coverage ~94% (gate 85%), Ruff clean
  (E/F/W/I/N/UP/B/C4/SIM), every file ≤150 code lines, CI on every push.
- Package `p2p_pursuit` under `src/`, Python 3.13, **uv only**. CLI:
  `uv run p2p-pursuit peer|sim|replay|smoke|authorize`. Business logic behind the `PursuitSDK`
  facade; every external call behind the Gatekeeper. Ports: thief 8801 / police 8802.
- Read before acting: `README.md` (full academic README — Dec-POMDP §1, orchestration
  dilemmas §2, strategy §3, RL-n/a §4, screenshots §5 with tracked-but-empty `docs/img/`
  paths, interpretation log §13), `docs/TODO.md` (**single source of truth for remaining
  work** — open items live in §0, §5, §8, §9), `docs/RUNBOOK.md` (tunnel + league ops;
  §3b = interop with reference-derived peers), `docs/STRATEGY.md`, `docs/PLAN.md` (ADR-2 =
  one codebase → two submission repos).
- Spec sources: rules book `police_thief_p2p.pdf` v3.0.0 (Hebrew RTL, 160 pp) lives in the
  reference repo `rmisegal/Game-P2P-Cop-Chase` under `docs/`; grading rubric
  `software_submission_guidelines-V3 (2).pdf` in `/mnt/c/Users/yosef/Downloads`. pypdf
  extraction of either needs bidi line-reversal post-processing (reverse each line, un-reverse
  Latin/digit runs, mirror brackets).

## Non-negotiable guardrails

1. **Secrets:** `credentials.json` / `token.json` / `.env` are git-ignored and must NEVER
   enter any repo history. Before every push to a *new* repo run
   `git log --all --diff-filter=A -- credentials.json token.json .env` and require empty.
2. **Never email the lecturer's address** (`rmisegal+uoh26finalgame@gmail.com`) from a test.
   Test sends go to the user's own address only; real reports fire only inside real matches.
3. **Quality gates stay green on every commit:** `uv run ruff check` zero violations;
   `uv run pytest --cov` ≥85%; files ≤150 code lines (split, never compress); TDD for new
   modules; tunables in `config/`, nothing hard-coded; uv only, never pip.
4. **Game integrity:** counted matches force exactly 6 sub-games (`--counted` enforces); one
   counted match per opponent, ≤10 total; truthful `--prior-counted` declaration; the live GUI
   shows **local truth only** (belief heatmap — rendering the opponent's real position
   disqualifies).
5. **Bookkeeping:** tick `docs/TODO.md` checkboxes as tasks complete; append significant
   prompts to `docs/PROMPT_BOOK.md`; keep the auto-memory file current.

## Remaining work, in dependency order

### A. Gmail OAuth (blocks league reporting; one human step)
Run `uv run p2p-pursuit authorize` — the **user** must complete the browser consent (the HW6
refresh token is dead: `invalid_grant`, Testing-mode 7-day expiry). Then set
`[email] mode = "send"` in `config/police/game.toml` AND `config/thief/game.toml`.
Verify with one send to the user's own address.

### B. Two-repo submission split (book §9.4 — graded; do BEFORE the first counted match)
1. With the partner, decide visibility: public, or private shared with `rmisegal@gmail.com`.
   Names per PRD open-parameters table: `p2p-police-agent` / `p2p-thief-agent`.
2. Write the sync script (TODO §0): workspace → both repos, full plain tree (no submodules —
   the grader must see files), per-repo role default, secrets excluded.
3. Each repo README: set the role line and the **sister-repo cross-link** (mandatory academic
   README item #6; cop README → thief repo and vice versa).
4. Each repo must independently contain: README + `config/` (incl. every match's agreed
   config) + `docs/PRD*` + `PLAN` + `TODO`. CI green in both. Secrets-history check (guardrail 1).
5. Record both URLs everywhere they're promised: both README headers ("Sister repositories"),
   the declaration/result 4-repo-links defaults, `docs/TODO.md` §0.

### C. Screenshots (needs a display — X server under WSL, or run on Windows)
Capture into `docs/img/` exactly per the README §5 table: `live_belief_heatmap.png`,
`replay_verified_ok.png`, `replay_tampered.png` (tamper drill — doctored log, exit code 3),
`league_match_terminal.png` (during the first real match). Then convert README §5 from a
path table into embedded images and sync to both repos.

### D. Live tunnel drill — GATE M5
ngrok or Localtonet account (human signs up). RUNBOOK §1–2: expose the thief peer
(`ngrok http 8801`), point the police's `opponent_url` at the public URL, run a full
sub-game across the internet, confirm mutual audit `Verified OK`. Tick TODO §5.

### E. League play — TODO §8 (needs opposing teams; the human schedules, you run)
1. **Warm-up interop first, uncounted.** Reference-derived peers expose
   `negotiate`/`receive_turn`/`submit_audit`/`receive_control`; ours is
   `handshake`/`receive_commit`→`receive_reveal`→`receive_event`/`audit_exchange`. Crypto
   content is identical; the wire contract is pair-negotiated — agree the surface in warm-up
   (RUNBOOK §3b); if adapting, a thin shim in `infra/mcp_client.py` + the service facade.
2. **Two counted matches vs two different teams:** negotiate a byte-identical `game.json`
   (minimums may only rise; handshake refuses on `config_sha256` mismatch), exchange the
   scent-model lock, truthful prior-counted declaration, 6 sub-games, mutual audit, result
   agreement, **both teams report independently** (a missing report forfeits that side's points).
3. **Per match:** archive artifacts + agreed config under `matches/` and commit (Appendix F);
   evidence kit = heatmap screenshot, `Verified OK` screenshot, terminal output, Gmail id.
   The playing commit hash lands in declaration + result automatically.

### F. Submission mechanics (book ch. 9/11 + Appendix C)
1. 8-char group code (no spaces) with the partner → record in TODO §0; use it in the tag.
2. Final sweep against the book's ch. 11.5 pre-submission checklist — every layer demoed.
3. Annotated tag on BOTH repos:
   `git tag -a v1.0-submission -m "Final submission: Police-Thief P2P, group <code>"` + push.
4. Moodle: download the form, fill without changing fields, save as PDF, **each member
   submits separately**; self-grade reflects code quality only, never match results.

## Human-only steps — don't block, prepare then ask once, precisely
Browser OAuth consent (A) · ngrok signup (D) · partner decisions: repo visibility (B1) and
group code (F1) · scheduling opposing teams (E) · Moodle uploads (F4). Everything else you do
autonomously; batch the asks instead of stopping repeatedly.

## Definition of done
`docs/TODO.md` has no unchecked boxes outside "External inputs"; both submission repos are
tagged `v1.0-submission` with green CI, a complete academic README with real screenshots,
per-match configs, and cross-links; ≥2 counted-match archives sit in `matches/`; no secrets
in any repo's history.
