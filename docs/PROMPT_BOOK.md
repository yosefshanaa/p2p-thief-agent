# PROMPT BOOK — Prompt-Engineering Log

The guidelines (§8.3) require documenting the significant prompts that drove the AI-assisted
development: context, intent, resulting output, and the iterative refinements. This project was
built **PRD-first** with Claude Code (Fable 5): every build stage was specified as a PRD *before*
any code was generated — the book's own rule ("define and demand full documentation before any
line of code"). The prompts below are the actual project-shaping instructions, in order.

## 1. Spec ingestion & planning

> *"Read police_thief_p2p.pdf … look at my HW6 … compare the final project's demands with the
> previous HW6 because it's already working. Make full PRD, PLAN, TODO files."*

**Context:** 160-page Hebrew rules book (RTL PDF — required a bidi post-processing script to
extract). **Output:** `docs/GAP_ANALYSIS.md` (HW6 is architecturally incompatible: referee vs.
zero-trust P2P), master `PRD.md` with the 55-rule compliance map + binding parameter table, seven
stage PRDs mirroring the book's §10.3 build order, `PLAN.md` (ADRs), `TODO.md` with binary gates.
**Refinement:** a second, deliberately critical pass was prompted ("run over them again and be
very critical") — it surfaced the unfixed first-mover, the three distinct timers, the full
declaration contents, the `github_commit` field name, and the academic-freedom clause.

## 2. Contradiction resolution (the key design prompt)

While drafting PRD-6 we hit the book's central tension: figure 6 says "Reveal: Move + Hint"
per step, but with public start positions a per-step move reveal makes both trajectories fully
computable — destroying the Dec-POMDP premise of ch. 1/4/6. The resolving prompt:

> *"Reconcile the commit-reveal figure with partial observability; check how the lecturer's
> reference implementation handles it."*

**Output:** the interpretation shipped in `domain/protocol.py` and the README interpretation
log — per-step Reveal carries the *public projection* only (hint, served scent, barrier
declarations); moves/nonces open at the sub-game audit. The reference repo's own
`protocol.py` ("nonce withheld … proven at the end-of-game audit") confirmed the reading.

## 3. Stage-by-stage implementation prompts

Each stage was implemented from its PRD as the instruction ("implement PRD-N; gate must pass
before the next stage"). Representative refinements that mattered:

- **Scent engine:** "use the book's figure-4 matrix as the emission kernel and its 0.9→0.81
  example as a golden test; round to 4 decimals so the audit recomputes bit-identically."
- **Protocol race:** a live two-peer MCP run produced a false TAMPERED verdict. Diagnostic
  prompt: "compare the sealed-record order to the live-hash order across concurrent peers."
  Fix: capture claims moved *inside* the reveal (atomic under the service lock) and audit
  pairing switched from positional to content-addressed (by digest) — also the robust choice
  for cross-team interop.
- **GUI:** "local truth only — the view-model must be unable to receive the opponent's
  position by construction, and a test must enforce it."

## 4. Strategy-optimization prompts (the graded core)

> *"Look at the strategies, optimize them — every strategy optimized, based on the rules."*

Method prompt: "snapshot the current brains from git as v2; build a cross-version tournament
harness; evaluate every candidate against BOTH generations before shipping." Iterations (full
numbers in `STRATEGY.md` §6):

1. Threshold recalibration — belief top-cell mass is ~0.15–0.3 under scent evidence, so v2's
   0.5/0.8 thresholds never fired (police: 0 claims, 0 barriers in instrumented games).
2. Thief risk-radius: captures against dropped 16→11 vs the old police — but 35 vs the new
   lead-pursuit police: straight flight is exactly what interception eats.
3. Situational juke (chase-only zigzag): 35→12. An always-on wander penalty was tried and
   **rejected on evidence** (27 captures — wandering slows escape more than it confuses).
4. Police interception rebuilt on scent-trail velocity instead of belief-peak deltas: 12→21.
5. Claim-frequency sweep on two independent seed ranges: 0.15 beat 0.10 (48:37) — every claim
   leaks our exact cell; fewer, better-timed claims win.

## 5. Compliance prompts

> *"Look at software_submission_guidelines-V3 … make sure everything is perfect."*

**Output:** SDK facade (single business-logic entry), Gatekeeper FIFO overflow queue,
versioning to 1.00, extended Ruff profile (N/C4/SIM), `.env-example`, this prompt book, the
cost analysis, and the parameter-sweep runner in `notebooks/`.

## 6. Continuation prompt

The remaining work (OAuth consent, two-repo split, screenshots, tunnel drill, league matches,
submission mechanics) is packaged as a single self-contained handoff prompt —
[`CONTINUATION_PROMPT.md`](CONTINUATION_PROMPT.md) — encoding the project state, the
non-negotiable guardrails (secrets, lecturer-address, quality gates, game integrity), the
dependency-ordered task list with acceptance criteria, and the human-only steps. Pasting it
into a fresh session resumes the project without re-derivation.

## 7. Executing the continuation prompt (2026-07-28)

Prompt: the full text of [`CONTINUATION_PROMPT.md`](CONTINUATION_PROMPT.md), pasted verbatim
into a fresh session. One session then delivered, unattended: the two-repo sync script
(`scripts/sync_repos.py`, TDD, tracked-files-only mirror so secrets are excluded *by
construction*, ROLE-marker role default wired into the CLI), creation of both submission
repos with green CI and verified-clean secrets history, and three of the four mandatory
README screenshots — captured from a **real** localhost two-peer match plus a genuine tamper
drill (forged `pos_after` → `TAMPERED` at the exact doctored frame, exit code 3). Notable
technique: under WSLg the X root window is not grabbable (rootless XWayland), so the capture
reads the Tk client window's own backing store via `python-xlib` `GetImage` — and the replay
shots drive the real `ReplayView` widget to a chosen frame before capturing it.

## 8. Frontend polish as a synced commit series (2026-07-28)

Prompt: *"work on the frontend in each one of them, also as want as much commits as we can."*
Interpreted as: many **real**, individually-gated commits — never empty padding, because
graders read history quality — with `scripts/sync_repos.py --push` run after each one so the
police and thief repos accumulate the same granular history as the workspace. The series
(each commit ruff-clean + unit-green): ① scent-trace overlay — closing the gap that
`scent_hex` existed but was never drawn; ② belief argmax ring + entropy readout, side panel
extracted into a tkinter-free `info_lines()`; ③ (row, col) coordinates matching the log
indexing + a legend strip generated from tested `legend_items()`; ④ role accent theming and
an end banner that colors win/loss from this side's perspective; ⑤ replay auto-play with
speed control; ⑥ keyboard navigation through a single clamped `_jump`; ⑦ frame slider +
match-identity header; ⑧ README §5 screenshots recaptured from a fresh live match showing
every new element at once (including a green `YOUR TURN` frame with the police standing on
the belief peak).

## 9. "Read the continuation prompt and continue" → interop, proven not assumed (2026-07-29)

With league play blocked on scheduling humans, the open work was the one item that needed no
opponent: the warm-up interop contract (TODO §8.1). Instead of designing against the runbook's
prose description of the reference peer, the first move was to **clone the reference repo and
read its source** — which immediately falsified our own documentation. The runbook claimed the
cryptographic content was "identical, a naming difference only". It is not: they hash
`canonical(payload)|nonce`, we hash the record with the nonce inside it, so neither side could
have verified the other. That would have surfaced in a *counted* match, at the audit, with
nothing to be done about it.

Two decisions followed, both put to the user because they changed the shape of the work:
adopt their digest behind a per-match `[interop] dialect` switch (default `native`, pinned
byte-identical by a golden vector), and validate against the real reference peer rather than a
mock. The live warm-up then earned its keep twice over — it found a crash in *their* reporting
caused by three fields our identity payload omitted, and a bug in *our* replay viewer that
stamped a clean interop match `TAMPERED`. Neither was reachable from unit tests written against
our own assumptions.

The transferable move: when an integration is described in prose, go read the other side's
code, and then actually run against it. Interop bugs live in the gap between two correct
implementations, and that gap is invisible from either side alone.

## Lessons that transfer

- **PRD-before-code works with AI agents**: every stage that had a written gate shipped green;
  the only protocol bug (the claim race) was in behavior the PRD hadn't pinned down.
- **Make the agent prove changes against a frozen baseline** (git-snapshot the old version) —
  self-play deltas alone are misleading; matrix evaluation caught two "improvements" that were
  regressions.
- **Golden numeric examples from the spec** (0.9→0.81) make disputes with a future opponent —
  or with your own refactor — decidable by a unit test.
