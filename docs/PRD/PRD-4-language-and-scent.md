# PRD-4 — Stage 4: Natural Language + Scent (book ch. 4 + 6)

**Objective:** the project's heart — replace injected ground truth with real uncertainty: pheromone
fields, decaying trails, free-language hints (which may lie), and the Bayesian belief map that
fuses them. This is the step where the Dec-POMDP becomes real.

## Scope
**In:** scent engine, belief engine, hint generation (4 provider modes) + hint parsing, trust
model, brains v2 operating on belief views, token metering.
**Out:** crypto sealing of the scent model (PRD-6 seals what this stage defines), tunneling.

## Functional requirements
1. **Scent engine (fixed params):** per move/stay emit a 5×5 radial field, center τ=0.9; after each
   full turn decay all cells: `τ(t+1)=max(0,(1−ρ)·τ(t)+Δτ)`, ρ=0.10; values continuous in
   **[0, 0.9]**. Symmetric: each peer
   maintains its own emission field and serves it to the opponent; each peer reads **only the
   opponent's** field. The model + a numeric example (0.9 → 0.81 after one decay) is exported as a
   canonical document for the pre-series cryptographic lock (#23) and our engine code may be
   shared with opponents (book recommendation).
2. **Belief engine:** posterior grid `b(s)` over opponent position.
   - Prediction: motion-model diffusion each turn (opponent moves ≤1 orthogonal step).
   - Scent update: likelihood from the emission+decay forward model (freshness ⇒ recency).
   - Hint update: parse hint → likelihood field scaled by **trust coefficient**; contradiction
     between hint and scent (book's "moved north / scent SE" case) lowers trust, boosts scent weight.
   - Output: normalized heatmap for GUI + argmax/entropy for brains.
3. **Hints out:** free natural language only, ≤`[hint word limit]` words (enforced by truncation
   + told to the LLM in its system prompt); `[map area]` landmark flavor when configured; Intent
   flag (truth/lie) chosen by the brain and recorded for the commit (PRD-6).
   Providers (private TOML `[trash_talk] provider`): `template` (default, 0 tokens) | `ollama` |
   `claude_api` | `claude_cli`; `every_n_steps` throttles LLM calls; provider failure falls back
   to template — **banter can never stall or decide a turn**.
4. **Hints in:** robust free-text parser (rule-based direction/landmark/distance extraction; no
   numeric-protocol assumption — #26–27 also binds the opponent, but tolerate anything).
5. **Brains v2:** police — pursue belief argmax with information-gain tie-break; barrier corridors
   against belief mass; hint deception policy (herding lies). Thief — maximize expected distance
   from police belief cloud × mobility; **scent-aware pathing** (avoid re-emission hotspots);
   **scent-consistent lies** (claim positions matching our stale trail).
6. **Token metering:** count LLM tokens per call/series vs `[token budget]` (~200k default);
   totals flow into the result artifact (#54).

## Milestone (binary gate)
> A free-language report is translated into inference (belief mass moves correctly); the scent map
> updates and decays each step per the formula (golden-value test incl. the 0.81 example); the LLM
> (or template) emits a hint honoring the word cap; a planted lie contradicting scent measurably
> drops the trust coefficient and the belief follows the scent.

## Tests
Unit: emission field golden matrix (5×5 values), decay series, belief normalization, motion
diffusion, trust update, parser corpus (true/false/garbled hints), word-cap enforcement, provider
fallback, token accounting. Integration: fog series police-v2 vs thief-v2 with seeded stats.
