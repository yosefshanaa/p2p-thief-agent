# PRD-3 — Stage 3: "Blind" Strategy Module (book ch. 6)

**Objective:** first version of the pluggable strategy module operating under *full information*
(opponent position known, injected by the dev harness) — isolate decision-core correctness from
uncertainty noise before scent/belief arrive in Stage 4.

## Scope
**In:** `BrainBase` plug-in contract, police brain v1, thief brain v1, dev harness with perfect
information, brain-vs-brain simulation runner for tactics evaluation.
**Out:** belief maps, scent, hints, LLM (Stage 4). RL is optional and deferred (extension backlog).

## Functional requirements
1. **Plug-in contract** (mirrors the reference repo so league opponents' mental model matches):
   private TOML `[strategy]` keys `police_class` / `thief_class` = `package.module:Class`;
   class subclasses `BrainBase`, overrides `_pick_move(view) -> Move` and (police) barrier choice
   `_decide_move(view) -> Move|BarrierPlacement`. Empty section ⇒ shipped default brain.
   The **view** never contains ground truth in live play; in this stage the dev harness injects it.
2. **Move safety:** whatever the brain returns is passed through the Stage-1 validator; an illegal
   choice falls back to a safe legal move (never forfeit on our own bug). LLM is never consulted
   for the move (#25) — enforced by design: the brain API has no LLM handle.
3. **Police brain v1:** shortest-path pursuit (BFS around barriers, Manhattan tie-break);
   barrier logic v1 — place only when it strictly reduces the thief's escape set and passes a
   **self-trap connectivity check** (flood-fill: police must retain a path to the thief region);
   barrier-capture when adjacent to the (known) thief cell.
4. **Thief brain v1:** mobility-aware evasion — maximize `(distance to police) + λ·(open escape
   routes)`; corner/edge avoidance early; barrier-aware pathing.
5. **Simulation runner:** N seeded headless games brain-vs-brain, win/step statistics — our
   tactics lab for the whole project (later re-used under fog).

## Milestone (binary gate)
> Given a known target cell, the agent computes and executes the shortest legal path with no
> manual intervention; police v1 captures a random-walk thief on 7×7 well under 35 steps in ≥95%
> of 100 seeded games; thief v1 survives a random-walk police ≥95%.

## Tests
Unit: BFS around barrier mazes, self-trap veto cases, mobility scoring, fallback-on-illegal.
Integration: seeded sim-runner statistics asserted as regression bounds.
