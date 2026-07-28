# PRD-7 — Stage 7: Reporting Shell, GUI & Replay (book ch. 7 + 9 + Appendix A)

**Objective:** the outer shell — Gmail-API automated league reporting behind a Gatekeeper, the
local-truth live GUI, and the hash-verifying Replay Viewer. Built last because it consumes every
layer beneath it.

## Scope
**In:** live Tkinter GUI, Replay Viewer, four JSON artifacts, Gmail OAuth + sender, Gatekeeper
(quota/token-bucket/DOS), league workflow automation (count declaration, result agreement, dual
reports).
**Out:** nothing — this completes the product.

## Functional requirements
1. **Live GUI (per peer, local truth only — #8–9):** belief heatmap (red intensity ⇒ higher
   P(opponent)); own position, barrier quota, step counter, opponent scent view, hint feed
   (sent/received with intent as known locally); **turn banner**: green `YOUR TURN` on turn
   receipt, gray `LOCKED` after our commit, input ignored while locked. `--no-gui` headless flag.
   No component may ever receive the opponent's true position.
2. **Replay Viewer (#20 — submission gate):** load `log_<game_id>_g<NN>.json`; step ⏮ ⏭ / play;
   every step re-runs the PRD-6 audit engine live; green **`Verified OK`** stamp per verified
   step / final; red **`TAMPERED`** banner voids the match view. Board here may show reconstructed
   positions (post-game evidence, not live play). Screenshots of heatmap + `Verified OK` are
   collected for the README.
3. **Four artifacts** (common `game_uid`, names from Appendix F §3):
   `declaration_<game_id>.json` (PRD-6), `config_<game_id>_g<NN>.json` (agreed constitution copy),
   `log_<game_id>_g<NN>.json` (sealed step log — commits, reveals, nonces, **hints and the
   LLM-discussion fields**), `result_<game_id>.json` (per-sub-game scores + totals, 4 GitHub
   links, per-sub-game `github_commit` hash, token totals). JSON-schema validated.
4. **Gmail reporting (#32–35):** after a valid match and explicit result agreement with the
   opponent, our peer **automatically** emails `result_<game_id>.json` (+ artifacts) as a **JSON
   attachment** — never plaintext — to `rmisegal+uoh26finalgame@gmail.com`. Independent of the
   opponent's report. `mode = draft|send` in private TOML (draft for dev, send for league).
5. **OAuth (Appendix A):** `gmail.send` scope **only** (#30); `credentials.json` + `token.json`
   created per the 5-step guide, **git-ignored before first commit** (#39–40); refresh-token flow
   ⇒ months of autonomy; mockable transport so all tests run without credentials.
6. **Gatekeeper (#28–29):** Quota Manager (daily send cap) → **Token Bucket**
   (`tokens←min(C,tokens+r·Δt)`; allow iff ≥1; config minimums 30 rpm / 2 concurrent / 5 s
   backoff / 3 retries / queue 100) → **DOS detector** (burst/loop anomaly ⇒ hard `LOCKED`,
   sacrificing the report to save the account); honor HTTP 429 with backoff, never insist.
7. **League workflow:** pre-match **truthful counted-game declaration** (#37–38); enforce one
   counted game per opponent (#52); warm-up flag excluded from counting; track ≥2 counted vs
   different teams (pass gate), ≤10 counted total.

## Milestone (binary gate)
> A finished match auto-produces all four artifacts, and a real (or draft-mode) Gmail lands with
> the JSON attached; the GUI shows live state through a full game; the Replay App replays a
> recorded series with `Verified OK`; a synthetic report-burst is throttled by the token bucket
> and a synthetic infinite loop trips the DOS lock.

## Tests
Unit: artifact schemas, bucket math over simulated time, DOS trigger, quota cutoff, 429 handling,
draft/send modes (mocked), GUI view-model (no-ground-truth invariant enforced by construction +
test), replay verdicts on good/tampered logs. Integration: end-to-end match → artifacts → report.
