# PRD-1 — Stage 1: Base Logic (book ch. 3)

**Objective:** the physical core of the game, no networking, no crypto, no AI. Both agents run in
one process against a local board model so that movement, barriers, capture and scoring are proven
before anything is layered on top.

## Scope
**In:** board, coordinates, move legality, barrier mechanics, capture detection, scoring, step/turn
counting, shared-constitution loading, deterministic local game loop (scripted/random walkers).
**Out:** MCP, scent, hints, LLM, crypto, GUI (a plain-text board printer is allowed for dev only —
it prints ground truth and therefore must live in a dev-only module never used in live play).

## Functional requirements
1. **Board** `[board size]`≥7×7, cells `(row,col)`, origin top-left, index 0 — all from config;
   invariant: agents and barriers occupy valid distinct cells (two agents may collide only as capture).
2. **Moves:** `N,S,E,W,STAY` exactly; validator rejects diagonals, off-board, into-barrier moves.
   The validator is the same code path later used to judge the *opponent's* revealed move (#13–14).
3. **Barriers (police):** placement only in a no-move turn; target = own cell or 4-adjacent;
   quota `[barrier quota]` (14 min) enforced; permanent; impassable to both.
   - Placement on thief's cell ⇒ **capture** (#46). Thief with zero legal moves ⇒ **capture** (#47).
   - Placement record carries the exact cell — the truth-declaration data (#15–16).
4. **Endings & scoring** (#48): capture 20/5; survival — thief reaches `[survival threshold]` (35
   min) valid steps ⇒ 5/10; technical loss 0/0; series tie ⇒ 2/2. Score table read from config.
5. **Constitution loader:** parse `config/game.json` (canonical form), validate against schema,
   compute `config_sha256`; parse private `game.toml`; JSON overrides TOML on shared keys (#11).
6. **Turn/step accounting:** step counter, `[move cap]` cutoff, "full turn" boundary event (needed
   later for scent decay).

## Interfaces (stable for later stages)
- `Board`, `Rules.validate(move, state) -> Legal|Illegal(reason)`, `Rules.apply(move) -> Event`
  (`moved|barrier_placed|captured|survived|technical_loss`), `Scoring.score(event)`,
  `ConfigManager.load(role) -> (shared, private, config_sha256)`.

## Milestone (binary gate, book §10.4)
> Two agents move legally on the grid; the 15th barrier is rejected; a diagonal is rejected;
> coordinate overlap triggers capture; barrier-on-thief and enclosure both capture; a scripted
> 35-step game ends in survival with correct scores.

## Tests
Unit: move legality matrix (all 5 moves × edges/barriers), barrier quota/adjacency/self-cell,
both capture-by-barrier paths, enclosure detection, scoring for all four endings, config
override precedence, canonical-hash stability across platforms (CRLF/ordering).
