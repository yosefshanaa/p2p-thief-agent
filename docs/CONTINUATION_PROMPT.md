# CONTINUATION PROMPT — finish the P2P Cops-and-Thieves final project

*Paste everything below this line into a fresh Claude Code session started in
`/mnt/c/Orch/final_Project` to continue exactly where the project stands.*

---

You are continuing the final project for Dr. Yoram Segal's **"Orchestration of AI Agents"**
(University of Haifa): a distributed cops-and-robbers game between two autonomous AI peers over
FastMCP — true P2P, **no referee**, every step sealed with SHA-256 commit → acknowledge →
reveal → mutual audit (tamper ⇒ technical loss 0/0). Team **`ahk-yosi`**: Yosef Shanaa
(213314859) + Ahmad Kaiss (325811255).

## State: the system is built, green, and has already played over the internet

- Workspace `/mnt/c/Orch/final_Project` → https://github.com/yosefshanaa/final_Project (`master`).
- **Submission repos (PUBLIC, CI green, group code `ahk-yosi`):**
  https://github.com/yosefshanaa/p2p-police-agent · https://github.com/yosefshanaa/p2p-thief-agent
  Publish with `uv run python scripts/sync_repos.py --push` — it mirrors **git-tracked files
  only** (so secrets cannot leak by construction), writes each repo's `ROLE` marker and README
  role banner + sister link, and refuses to push on a dirty secrets history.
- ~105 tests, **93.4% coverage** (gate 85%), Ruff clean, every file ≤150 code lines.
- Read first: `docs/TODO.md` (**single source of truth for remaining work**), `README.md`,
  `docs/RUNBOOK.md` (tunnel + league ops; §6 holds the live-drill evidence), `docs/STRATEGY.md`,
  `docs/PLAN.md`, `docs/COST_ANALYSIS.md`.
- Spec: rules book `police_thief_p2p.pdf` v3.0.0 lives in `rmisegal/Game-P2P-Cop-Chase` under
  `docs/`; grading rubric `software_submission_guidelines-V3 (2).pdf` in
  `/mnt/c/Users/yosef/Downloads`. Both are Hebrew RTL — pypdf extraction needs bidi
  line-reversal post-processing (reverse each line, un-reverse Latin/digit runs, mirror brackets).

## Interop is built and proven — do not redesign it

Reference-derived opponents were the biggest un-de-riskable unknown. It is now closed:

- `uv run p2p-pursuit smoke <url>` reports `dialect=native|reference|unknown` from their tool
  listing. Run it against every new opponent before anything else.
- `[interop] dialect = "reference"` in `config/<role>/game.toml` switches the whole adaptation:
  their tool names, their push/inbox framing, **and their commit formula**.
- **The runbook used to claim the crypto was "identical". It is not** — they hash
  `canonical(payload)|nonce`, we hash the record with the nonce inside it. Neither side can
  verify the other until one adopts the other's digest. That is what interop mode does; the
  native path is unchanged and pinned by a golden vector.
- **Warm-up played 2026-07-29 against the lecturer's unmodified reference peer**: full 35-step
  sub-game, their audit of us `log_verified: true`, ours of them `Verified OK`, scores agreed.
  Evidence + reproduction: `matches/warmup-reference-interop/`. Details: RUNBOOK §3b.
- Interop caveats that are real and documented: no mutually enforceable scent-model lock, their
  claim answers/win claims are unsealed, and they never return their verdict of us (so our
  result honestly reports `mutual_agreement: false` for such a match). **Prefer the native
  dialect for counted matches** when the opponent will run the shim.

## Already done — do not redo

Gmail OAuth (consent complete, `[email] mode = "send"` in both configs, verified by a real send
to `apexmediamind@gmail.com`, Gmail id `19faaa37fd641748`) · two-repo split · README §5 with
three of four real screenshots · GUI polish (scent overlay, belief-argmax ring, entropy readout,
coordinates, legend, role theming; replay auto-play, keyboard nav, frame slider, metadata
header) · **GATE M5** (full sub-game across public tunnels with both sides `Verified OK`;
tunnel-kill drill → clean `technical_loss` 0/0, state persisted, no hang) · OpenAI banter
provider live · watchdog-vs-turn-timeout bug fixed (see below).

## LLM banter — configured and working

`[trash_talk] provider = "openai"`, `[llm] model = "gpt-5.4"` in **both** role configs. The key
lives **only** in git-ignored `.env` (`OPENAI_API_KEY`) — never in `config/`, because config
files are exchanged with the opponent and hashed into `config_sha256`. Moves are **always pure
Python** (book rule #25); the LLM only writes the ≤15-word taunt. Three live-tested traps, all
fixed — do not regress them:

1. The gpt-5.x family **rejects `max_tokens`** ("Unsupported parameter"); use
   `max_completion_tokens` (older models accept it too).
2. Reasoning models return **empty text on a small budget** — `gpt-5.6-luna` produced nothing at
   60 tokens. Budget is 400; the 15-word cap is applied by `clip_words` afterwards, never by
   starving the budget.
3. `import openai` (~31 s on WSL) and the first request (~22 s) each exceed the 30 s turn
   deadline — both are paid at startup, SDK retries are disabled, and one call is capped at
   `deadline // 3`.

Measured: ~70 tokens and 1.1–2.3 s per call, ~29k tokens per 6-sub-game series. Note that
`produce()` swallows every error into the template fallback, so **a broken provider looks
perfectly healthy while silently reporting 0 tokens** — after any change here, confirm token
counts are non-zero.

## Non-negotiable guardrails

1. **Secrets:** `.env`, `credentials.json`, `token.json` are git-ignored and must NEVER enter any
   repo history. Before pushing to a *new* repo, this must be empty:
   `git log --all --diff-filter=A -- credentials.json token.json .env`
2. **Never email the lecturer** (`rmisegal+uoh26finalgame@gmail.com`) from a test. Test sends go
   to `apexmediamind@gmail.com` only; real reports fire only inside real matches.
3. **Run the FULL suite before every push** — `uv run ruff check && uv run pytest --cov`.
   CI once sat red across several commits because only `tests/unit` had been run.
4. Files ≤150 code lines (split, never compress); TDD for new modules; tunables in `config/`,
   nothing hard-coded; **uv only, never pip**.
5. **Game integrity:** counted matches force exactly 6 sub-games (`--counted` enforces); one
   counted match per opponent, ≤10 total; truthful `--prior-counted`; the live GUI shows **local
   truth only** (rendering the opponent's real position disqualifies).
6. Tick `docs/TODO.md` as tasks complete; append significant prompts to `docs/PROMPT_BOOK.md`;
   keep the auto-memory file current.

## Environment traps that have already cost hours — read before running anything

- **`pkill -f "p2p-pursuit peer"` kills the calling shell.** Put it last in a command, or target
  exact PIDs. Similarly **`pgrep -f <pattern>` matches its own shell**, so it reports a process
  that has already exited — this produced a false "the peer is hung" conclusion. Verify with
  `ps -eo args --no-headers | grep "[p]attern"` instead.
- WSL: the X **root window is not grabbable** (rootless XWayland). Capture Tk windows via
  python-xlib `GetImage` on the client window — the `xcap.py` / `replay_shot.py` pattern is
  described in `docs/PROMPT_BOOK.md` §8.
- A full local 6-sub-game match takes ~4 minutes.
- `ss -tln` does not reliably show the peer's port here. Probe with `curl` instead: a healthy MCP
  endpoint answers a malformed POST with **406**, and a live tunnel with no origin gives **502**.

## Remaining work

### A. League play — the only real blocker (needs opposing teams; the human schedules, you run)

1. **Warm-up interop first, uncounted.** The shim exists and is proven (see above): probe with
   `smoke`, set `[interop] dialect` to match, play one uncounted sub-game, confirm both audits.
   Never discover a contract mismatch inside a counted match.
2. **Two counted matches vs two different teams:** negotiate a byte-identical `game.json`
   (minimums may only rise; the handshake refuses on `config_sha256` mismatch), exchange the
   scent-model lock, declare prior-counted truthfully, play 6 sub-games, mutual audit, agree the
   result, and **both teams report independently** (a missing report forfeits that side's points).
3. **Tunnel choice:** use a **Cloudflare quick tunnel**
   (`cloudflared tunnel --url http://localhost:8801`, no account, already installed). ngrok is
   installed and authenticated, but its **free tier drops the long-lived MCP session mid-game**
   while the agent itself stays healthy — treat it as handshake-capable only. Both peers must
   start within the connect window or one exits with `opponent never came up`.
4. **Provider for counted matches:** consider switching `[trash_talk] provider` back to
   `"template"` (0 tokens, no network inside the turn) unless the opponent agrees to LLM banter —
   the token budget is negotiated per match. `every_n_steps = 1` means ~420 calls per series
   (~10 extra minutes); 3 cuts that by two-thirds with no strategic loss.
5. **Per match:** archive artifacts + the agreed config under `matches/` and commit (Appendix F).
   Evidence kit: heatmap screenshot, `Verified OK` screenshot, terminal output, Gmail id. The
   playing commit hash lands in the declaration and result automatically.

### B. Last screenshot

`docs/img/league_match_terminal.png`, captured during the first counted match; then embed it in
README §5 (the other three are already embedded as images) and sync to both repos.

### C. Submission mechanics (book ch. 9/11 + Appendix C)

1. ~~Final sweep against ch. 11.5~~ **done** — `docs/SUBMISSION_CHECKLIST.md` maps every item of
   ch. 11.5 *and* the ch. 11.6 submission list to evidence. Layers 1–5 are green; items 6 (both
   sides' Gmail reports) and 7 (the tag) wait on a counted match by design.
2. Annotated tag on **both** repos, then push:
   `git tag -a v1.0-submission -m "Final submission: Police-Thief P2P, group ahk-yosi"`
3. Moodle: download the form, fill it without changing fields, save as PDF, **each member
   submits separately**; the self-grade reflects code quality only, never match results.

## Human-only steps — batch the asks, never block on them

Scheduling opposing teams (A) and the Moodle uploads (C3). Everything else is yours to do
autonomously. Repo visibility, the group code, Gmail OAuth consent, the OpenAI key and the ngrok
account are **all already done**.

## Definition of done

`docs/TODO.md` has no unchecked boxes outside "External inputs"; both submission repos are tagged
`v1.0-submission` with green CI, a complete academic README with all four real screenshots,
per-match configs and sister cross-links; ≥2 counted-match archives sit in `matches/`; and no
secrets appear in any repo's history.
