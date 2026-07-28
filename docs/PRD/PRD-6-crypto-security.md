# PRD-6 — Stage 6: Security & Cryptography (book ch. 5)

**Objective:** wrap the proven remote communication in the commit-reveal integrity layer: sealed
moves, nonce lifecycle, mutual audit, step-0 declarations, and the cryptographic locks on the
constitution and the scent model. After this stage, cheating is mathematically self-defeating.

## Scope
**In:** commit/verify primitives, protocol integration into the turn loop, audit engine, step-0
declaration, config & scent-model locks, capture-claim honesty path, tamper forfeiture.
**Out:** replay viewer UI (PRD-7 renders what this stage verifies).

## Functional requirements
1. **Commit primitive:** `H = SHA256(canonical_json(record))` where the sealed record covers
   `{state, move, intent(truth|lie), hint, verdict, step, role, sub_game, nonce}`; canonical JSON =
   sorted keys, fixed separators, UTF-8 — byte-identical across peers/platforms (#17).
   Nonce: `secrets.token_hex(16)`, fresh per commit, secret until final audit (#18);
   comparisons via `secrets.compare_digest`.
2. **Protocol in the state machine:** COMMITTING sends `H` only → opponent **Acknowledge** (locked)
   → **Reveal** (move + hint + intent; nonce withheld) → VERIFYING checks reveal legality vs
   Stage-1 rules and consistency with our view → at game end **Final Audit**: exchange all nonces,
   re-hash the opponent's entire log; any mismatch ⇒ `TAMPERED` ⇒ technical loss 0/0, immediately,
   no appeal (#19).
3. **Capture Claim / win claims:** police's claim triggers the thief's cryptographically bound
   truthful answer (#21–22); the answer rides a sealed record, so a lie is provably caught at audit.
   Same discipline for survival claims and barrier declarations (#15–16).
4. **Step-0 declaration (#24, #53):** build `declaration_<game_id>.json` fixing everything
   constant for the match: both teams' identities + members, all four repo URLs, both MCP server
   addresses, per-side hardware (OS, CPU cores/freq, RAM, GPU/VRAM), LLM model, the **agreed token
   cap**, code version, game number, **git commit hash being played** (also emitted later as
   `github_commit` in the result JSON), and game start/end times; hash-sign and exchange before
   move 1. Token consumption meter sealed into the result (#54).
5. **Constitution & scent-model lock (#11, #23):** pre-series exchange of `config_sha256` and the
   scent-model document hash (formula + numeric example); mismatch ⇒ refuse to play.
6. **Audit engine as a library:** `verify_step(entry)->OK|TAMPERED`, `audit(log)->verdict` —
   consumed by the turn loop, by the Replay Viewer (PRD-7), and by tests.

## Milestone (binary gate)
> A move is committed, acknowledged, revealed and verified with a valid nonce over the wire;
> step-0 declarations exchange and validate; a unit-tampered log entry is flagged by the audit
> engine; a full remote game ends with a clean mutual audit.

## Tests
Unit: commit/verify round-trip, canonicalization stability (key order, unicode, platform), nonce
uniqueness, every tamper class (move, hint, intent, state, nonce, hash), capture-lie detection,
declaration schema. Integration: full series with audit; adversarial peer harness that cheats in
each way and must always be caught.
