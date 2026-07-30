# STRATEGY — Move Policy & Tactics (the graded core)

Living document. The book makes the movement policy "the core of the grade" (Appendix F §5) and
mandates a **separate strategy module** plugged into the PeerRuntime *after* hint decode and
*before* commit pack (ch. 6.2). Requirements live in [`PRD.md`](PRD.md) §8 and
[`PRD/PRD-3`](PRD/PRD-3-strategy-blind.md)/[`PRD-4`](PRD/PRD-4-language-and-scent.md); design
rationale in [`PLAN.md`](PLAN.md) §6. This file tracks the **actual shipped doctrine per version**
and the evidence behind it — it also feeds the mandatory "strategies implemented" README section.

## 1. Binding constraints (from the book)
- Move decision is **always pure Python** — heuristics (Manhattan + Bayesian belief), our own
  algorithm, or optional RL; three equal paths (ch. 6.3). The LLM is banter-only (#25); LLM-driven
  tactics only by explicit mutual agreement — not our default.
- Plug-in contract: `[strategy] police_class` / `thief_class` = `package.module:Class`
  subclassing `BrainBase`, overriding `_pick_move` (+ `_decide_move` for the police barrier
  choice). Private per-peer choice — never negotiated, never shared with the opponent.
- Every brain output passes the rules validator; illegal choice ⇒ safe legal fallback (we can
  never technical-lose on our own brain bug).

## 2. Doctrine v1 (blind stage — full information via dev harness)
- **Police:** barrier-aware BFS pursuit, Manhattan tie-break; barrier placement only when it
  strictly shrinks the thief's escape set AND passes the flood-fill self-trap veto.
- **Thief:** maximize `distance(police) + λ·mobility` (open orthogonal neighbors), corner
  avoidance, barrier-aware pathing.
- Acceptance: v1 police captures a random walker ≤35 steps in ≥95% of 100 seeded games; v1 thief
  survives a random walker ≥95%.

## 3. Doctrine v2 (fog — belief-driven, the real game)
**Shared belief engine:** posterior grid = motion diffusion ⊕ scent likelihood (emission+decay
forward model; freshness ⇒ recency, τ≈0.81 ⇒ adjacent last turn) ⊕ hint likelihood × trust
coefficient `w`. Trust: corroboration ⇒ `w↑`; scent contradiction (book's "north claim / SE
scent" case) ⇒ `w↓` hard.

**Police:**
- Pursue belief argmax by barrier-aware BFS; tie-break by expected posterior-entropy reduction
  (information-gain patrol when belief is flat).
- Barrier doctrine (quota 14, each costs a full turn): early — none; mid — corridor pinching once
  belief mass ≥ threshold near an edge; end — pocket sealing with ≥2 quota reserved; kill shot —
  barrier **onto** a near-certain adjacent belief cell (barrier-capture). Invariant: flood-fill
  connectivity check before every placement.
- Deception: herding lies (announce false position pushing the thief toward sealed pockets);
  intent flag sealed in the commit.

**Thief:**
- Objective: `E_belief[dist(police,·)] + λ·mobility − μ·scent_risk`; never STAY twice
  (re-emission concentrates τ); increase distance from own scent centroid.
- Barriers are declared truth — reroute around forming pockets immediately.
- **Scent-consistent lying:** claim the region our *decayed* trail supports (3–4 turns stale) so
  the opponent's contradiction detector reinforces the lie; sprinkle true hints to keep their
  trust in us exploitable. Read the police's scent to infer patrol and steer orthogonally to the
  approach axis.

## 4. Evaluation protocol (regression-gated)
Seeded sim-runner tournaments in CI: v-next vs v-prev, vs random, vs the reference-repo greedy
brain; tracked metrics — police capture rate + mean capture step; thief survival rate; lie
detection/exploitation rates. Bounds asserted in CI; findings and parameter sweeps appended here
per version (this doubles as academic-README evidence).

## 5. Extensions backlog (excellence)
Particle-filter belief · bounded expectimax endgame · articulation-point barrier analysis ·
opponent-adaptive lie policy · auto-negotiation advisor — details in `PLAN.md` §6.5.

## 6. Version log
| Version | Change | Evidence |
|---|---|---|
| v2.0 | First fog doctrine: belief pursuit + entropy tie-break, kill-shot/corner-seal barriers with flood-fill veto, mobility+scent-centroid evasion, scent-consistent lies; claim answers exploited both ways (denial ⇒ negative evidence; claim ⇒ thief's belief collapses to claimant's cell). | 72 sub-games: 16 captures, police 600 : thief 640; all audits `Verified OK` |
| **v3.0 (shipped)** | **Police:** true interception — thief velocity estimated from the *scent trail* (freshest-cell displacement, cleaner than belief-peak jitter), pursuit-curve solve `pos = fresh + v·(1+k)` for the first reachable meeting point; disciplined claims (0.15 — every claim leaks our exact cell, so fewer + better-timed; sweep-validated on two seed ranges); kill-shot 0.30, corner-seal 0.20/dist 3. **Thief:** claim-radius risk term (belief mass within BFS ≤2 of candidate — where claims/kill-shots strike), forward-projection avoidance (mirror of lead pursuit), situational **juke** (break straight lines only under close pursuit — always-on zigzag measurably *hurts*: it slows net escape), two-ply mobility, corner discipline first half. | Cross-version matrix, 72-game cells: v3T cuts old-police captures **16→11**; v3P vs v3T **54/144 (37.5%)** and vs old thief 31/144 — above the 25% break-even vs the modern evader. Baselines: police captures a random walker **27/30**, thief survives a random police **30/30** (CI-gated). |

| **v4 (shipped 2026-07-30)** | Found by *instrumenting real games* rather than reasoning about the code. **Police:** ambush the belief peak for exactly one turn then step back onto the cloud (v3 froze on it — 21% of all turns were idle `STAY`, because standing on the argmax scored distance 0 and nothing could beat it); reversal as a tie-break penalty (28% of real moves were A→B→A step-backs); barrier thresholds relative to a *rolling window* of recent peaks. **Thief:** forward projection off the pursuer's scent trail instead of the jittery belief peak; barrier-aware BFS for the "chased" test; corner discipline for the whole game, scaled by the pursuer's remaining (publicly declared) quota; the lie sampled from several stale candidates with our private rng. | Cross-version matrix, 36 sub-games over **two** seed ranges. **Against the strongest thief the old police was helpless — 0/36 captures — where v4 takes 41.7%.** vs the frozen thief 33.3% → 41.7% (+8.4pp). v4 thief is **never captured** by the v3 police (0/36 vs 12/36). Cost: vs a random walker 90% → 83.3% (CI gate ≥70% still passes 8/10). |

Tuning lessons recorded for the README report: (1) always-on zigzag loses — straight flight is
fast, wander is slow; juke only when chased. (2) Claim frequency is an information price, not
free tempo — 0.15 beat 0.10 on fresh seeds 48:37. (3) Scent-trail velocity beats belief-peak
velocity as an interception signal (the belief peak jitters under hint noise).

### Where v4 stands against a *foreign* brain (the honest gap)

The matrix above is self-play: v4 against our own frozen lineage. Measured against the
lecturer's reference implementation over single sub-games on localhost:

| Pairing | v3 | v4 |
|---|---|---|
| our thief vs their police | 5/5 survived | 5/5 survived |
| our police vs their thief | 0/5 captures | **0/5 captures** |

So the police gains — real and repeatable against our own thief lineage — **do not transfer to
their evader**. That is the open question for the next iteration, and it deserves a hypothesis
rather than more tuning: our interception reads the freshest cell of the served scent field, and
their scent model decays *subtractively* with a linear-Chebyshev falloff where ours decays
multiplicatively with the book's figure-4 kernel. A velocity estimator tuned on one field shape
need not be sharp on the other. Worth testing before assuming the pursuit doctrine itself is at
fault.

Also worth noting for the league: over ten completed external matches, every single one was won
by whichever side played thief. With role alternation over six sub-games, a series in which
nobody captures scores 45–45 — a tie. **Capture ability as police is the only source of edge**,
which is why it is where the remaining effort belongs.

### The capture bound, and why the police cannot simply be tuned harder

Three experiments (2026-07-30) that together explain the 0/5, all reverted:

7. **Their scent field names their exact cell — and using it directly is a 41.7-point
   regression.** Instrumenting a live match against ground truth from their own revealed audit
   log: their served field's freshest cell was their true position **34/34 turns, mean error
   0.00**, while our Bayesian posterior averaged 0.47 off. Targeting the raw cell instead of the
   posterior nonetheless dropped our police from 41.7% to **0%** against our own thief, and
   changed nothing externally. The reason is a serving convention: we serve *pre-emission*
   (interpretation #4), so our own freshest cell is one step stale, and the belief map's job is
   precisely to diffuse that lag forward. **The posterior is not decoration** — a raw sensor
   reading is not an upgrade over a correctly specified filter.
8. **A perfect position estimate still does not capture.** With the exact cell known every turn,
   the police went **0/5** against the reference evader. That is the classic pursuit-evasion
   result: one equal-speed pursuer cannot capture on open ground however well it tracks. Capture
   requires removing space.
9. **But 35 steps cannot fund a fence.** A cornering doctrine (`walling.py`: spend barriers to
   cut the evader's BFS-reachable region, gated on knowing the exact cell — the condition the
   earlier area-denial attempt lacked) fired only ~2 times per game, because a single barrier
   adjacent to the pursuer rarely cuts 2+ cells from a ~40-cell region, and a wall that actually
   halves a 7×7 costs ~7 placements plus travel. Implemented, measured, removed.

### Resolved: it was never the timing — it is the *evader's* estimate of the pursuer

The reference's entire evasion policy is three lines (maximise distance from the believed cop
cell, tie-break on unvisited cells), our police catches that policy **36/36** when ported into our
engine, yet their real peer is never caught. Measuring both sides' estimates against ground truth
settles why:

| Estimator | Mean error | Exact |
|---|---|---|
| our police's belief of **their** thief (live) | **0.47** | 71% |
| our police's belief of **our** thief (sim) | **2.34** | 0% |
| our thief's belief of the police (sim) | 1.85 | 26% |

Two conclusions, and the first is counter-intuitive: our police has *better* information against
their thief (0.47) and captures **0%**, while it has *worse* information against ours (2.34) and
captures **41.7%**. Tracking is not the binding constraint — **the evader's estimate of the
pursuer is.** Their thief flees a well-informed estimate and is uncatchable; a distance-maximiser
fed our diffuse posterior (1.85 off, exact only 26% of the time) flees a phantom and walks into
the pursuer, which is exactly what 36/36 measures.

The second is that **our concealment is our real edge**: an opponent modelling us is 2.34 cells
off where we are 0.47 off modelling them, because we serve scent pre-emission and they serve it
post-deposit. That asymmetry, not our pursuit, is why we have never lost a sub-game externally.

Acting on it: the thief now blends the pursuer's trail cell into its distance term (`W_TRAIL`).
Honest effect size — on the tuning seeds it cut captures 41.7% → 27.8%, but that value was chosen
as the best of five, and on **50 untouched hold-out seeds** it is 30.0% → **26.0%**: a consistent
direction on both sets and a sound mechanism, but only two games in fifty, so not statistically
established. Shipped on the mechanism, not the number.

## 7. v5 — the squeeze (book §3.4), and what it does *not* prove

Re-reading §3.4 showed the earlier "barriers lose" conclusion was a verdict on our
*placement policy*, not on the mechanic. The book is emphatic: the quota "is the heart of the
police's strategic challenge", the police is "an **architect of the arena**", and it must
"**squeeze the thief into a corner** without blocking its own access routes". Most importantly it
names a **third capture path** we had implemented but never played for: *a thief with no legal
move — every neighbour a barrier or the board edge — is captured.*

That changes the arithmetic completely. Landing on a moving equal-speed evader is near-impossible;
enclosure costs **2 barriers in a corner, 3 on an edge, 4 in the open**. So `squeeze.py` closes the
evader's exits one at a time, and the police aims at the *door* rather than the evader.

Two calibration findings, both counter-intuitive and both measured:

- **Gating the doctrine ruins it.** Restricting the squeeze to a "cornered" quarry
  (exits ≤ 3, range ≤ 3) scored 22%/3%; ungated it scored 75%/78%. The placement rule already
  supplies the only gate that matters — a barrier must go within one step of the police, so a
  door can only be closed from beside it.
- **But it must be conditional on the quarry actually evading.** Squeezing a random walker cost
  25/30 → 20/30, because a walker does not flee and plain chasing catches it. The switch is
  "the gap has not closed in `GAP_WINDOW` turns". That window is knife-edge: 2 → 6%, 3 → 76%,
  **4 → 92%**, 5 → 26%.

| Police capture rate | v4 thief | v3 thief | reference policy | random walker |
|---|---|---|---|---|
| v4 (chase only) | ~30% | ~42% | 100% | 83% |
| **v5 (squeeze)** | **90–98%** | **92%** | **100%** | **93%** (gate 10/10) |

Validated on two seed sets never used for tuning (4000–4049, 5000–5049).

### The caveat that matters more than the number

**None of it transfers to the live reference peer: still 0/5.** Instrumenting the live match shows
why — the squeeze fired only twice, always the same two cells, because it needs the police
adjacent to one of the evader's exits and the reference thief never lets us that close. So the
90–98% is measuring **our own thief's willingness to be approached, not our police's strength**,
and self-play remains an unreliable predictor of league performance.

The same caution cuts the other way, and is why the thief was *not* rewritten to answer the
squeeze: in-sim our thief is caught 97.5% by our own v5 police, yet live it has never been caught
at all. An anti-squeeze term was implemented and measured at **zero effect at every weight**
(including after fixing a radius bug — the trail reports where the pursuer *was*, so a barrable
door lies within two of it, not one), and was removed rather than shipped as decoration.
Over-fitting the evader to a simulation that disagrees with every live result would be the wrong
trade. **Establishing why the sim and the wire disagree remains the single highest-value piece of
work on this project.**

### v4 negative results — kept on the record because they cost real effort

4. **Barriers are a tempo trap on this board, and the quota is a red herring.** The book grants
   14 barriers (29% of a 7×7 board) and v3 spent *none* — which looked like a glaring waste until
   it was measured. A placement forfeits the move, and a swept trade-off says the tempo is worth
   more than the area: at `BELIEF_FLOOR` 0.10 the police placed 2.45 barriers/game and captured
   **20%**; at every floor from 0.18 up it placed none and captured **45%** — identical to a
   barriers-off control. An explicit area-denial doctrine (place when the barrier measurably
   shrinks the thief's BFS-reachable region) was implemented, measured at **zero** effect, and
   deleted rather than left as decoration. Barriers therefore remain a rare kill shot only.
5. **A threshold calibrated by eye can be silently unreachable — and the fix can repeat the bug.**
   v3's kill shot needed 0.30 while the posterior peak never exceeded 0.294 over 385 measured
   turns, so rule #46 never fired. The first fix (a ratio of the *all-time* peak) reproduced the
   defect exactly: step 1's belief is a delta on the known start cell, `b_max = 1.0`, which pins
   the reference at 0.85 forever. Only a **rolling window** that forgets the opening certainty
   actually fires. Lesson: any threshold on a derived quantity needs its distribution measured,
   not estimated.
6. **Retargeting must stay on the cloud.** Stepping off the peak toward the globally second-best
   cell scored best against the heuristic thief (+19.5pp) but abandoned the probability cloud and
   broke the random-walker gate (6/10). Stepping to the adjacent cell with the richest local mass
   passes the gate at 8/10 and keeps +8.4pp. The bigger number was not shipped: a doctrine that
   only beats one opponent class is overfitted, and weakening the gate to admit it would have been
   moving the goalposts.
