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

## 8. v6 — offline policy search (`learn/`), and the sweep it caught out

Everything above was tuned by hand, one coordinate at a time. That is a defensible way to work —
each number in v4/v5 has a measurement behind it — but it has a specific blind spot, and v6 found
it: **a one-dimensional sweep can only ever report the best value of one parameter given the
current value of every other**. Where two parameters interact, the sweep reports a local verdict
and calls it a general one.

### The method

`src/p2p_pursuit/learn/` runs the cross-entropy method over the doctrine vector
(`strategy/params.py`, 23 fields — every constant either brain reads). It is policy search:
sample policies, keep the elite quarter, refit the sampling distribution, repeat. Three details
make it trustworthy on a noisy objective, and each has a test:

- **Common random numbers** — every candidate in a generation is scored on the same seed set, so
  comparing two candidates is not comparing two different sets of lucky games.
- **Elitism** — the running mean is re-scored each generation and competes with its own children,
  so one lucky elite set cannot walk the distribution downhill.
- **A variance floor** — without it the distribution collapses into the first plausible basin
  after three or four generations and merely *looks* converged.

The objective is **league points per sub-game**, not capture rate. The table pays 20/5 as police
and 5/10 as thief, so a doctrine can win the capture metric and lose the league.

### The opponent pool is the actual contribution

§7 ends by admitting that 90–98% in simulation coexisted with 0/5 on the wire, because the only
evader in the simulation was our own thief. So candidates are scored against a *population*:
`random`, `momentum` (straight-line runner), `greedy` (distance gradient), `hound` (trail
chaser), `noisy` (gradient + ε), `barrier` (a police that spends its quota freely — the doctrine
v4 measured its way *out* of), `holder` (an evader that preserves mobility instead of maximising
distance, i.e. the one archetype that resists the squeeze), and `mirror` (ourselves).

Each archetype declares **which roles it is genuinely distinct in**, and that is not bookkeeping.
Measured: as a thief, `greedy`, `hound` and `barrier` play a byte-identical trajectory, and as a
police, `greedy` and `holder` do. Listing them in both roles would have scored our police against
the same greedy evader three times out of eight — tripling one behaviour's weight in the
objective, which is the very over-fitting the pool exists to prevent.

### Police result — and the negative result it overturns

20 generations × 36 candidates × 40 training seeds, validated on hold-out seeds 9000–9039 that
the search never saw:

| Opponent (as thief) | v5 police | v6 police |
|---|---|---|
| `holder` (resists the squeeze) | 13.25 | **20.00** |
| `random` | 18.13 | **20.00** |
| `noisy` | 18.13 | **20.00** |
| `momentum` | 15.13 | 15.13 |
| `greedy` / `mirror` | 20.00 | 20.00 |
| **mean points/sub-game** | **17.44** | **19.19** |
| capture rate | 83% | **95%** |

The interesting part is *where* it went. Two hand-measured verdicts were reversed together:

- `belief_floor` **0.22 → 0.069** — v4 swept this alone and concluded "barriers are a tempo trap
  on this board" (§7, negative result 4).
- `gap_window` **4 → 2** — v5 swept this alone and measured 2 → **6%**, calling the window
  knife-edge (§7).

Neither reversal is valid on its own; *together* they are. A low barrier floor pays only if the
police starts closing doors early, and early squeezing pays only if it is allowed to spend
barriers freely. Each sweep held the other parameter at a value that made its own answer look
obviously right. The pair was never on the same axis, so no one-dimensional sweep could have
found it — and the biggest single gain is against `holder`, the archetype built specifically to
beat a squeeze, which is where a barrier-active police should show up if it works at all.

The remaining hole is `momentum`, unmoved at 15.13: a straight-line runner on an open board is
the classic pursuit-evasion result — an equal-speed pursuer cannot close on it — and the tuner
correctly declined to trade points elsewhere pretending otherwise.

### Thief result — and the co-evolution round that was worth running

The thief was searched the same way. Round 1 (against the *v5* police, 40 hold-out seeds):
**9.04 → 9.50** points, survival 81% → 90%. But that measured the thief against a police that no
longer existed, so round 2 re-ran it with `mirror` set to the newly tuned police: **5.25 → 9.75**
against the current police — from caught 95% of the time to caught ~5%.

That is the answer to §7's open item. The v4 anti-squeeze *term* measured zero effect at every
weight, twice. The search found the answer was never a new term: it roughly **doubled the
claim-radius risk weight** (`w_risk` 3.0 → 6.6, `w_lead_risk` 1.5 → 2.5) and *relaxed* the
discipline penalties it had been fighting with (`stay_penalty` 1.2 → 0.05, `corner_penalty`
0.5 → 0.24). Hand-tuning could not find it because it required moving four coupled weights at once
in opposite directions.

**The ladder was stopped at two rounds, deliberately.** A third would tune our thief against our
own police and vice versa — improving a matchup with nobody in it but us, which is precisely the
self-play failure mode this section opened by describing.

### Combined result, and the honest caveats

On validation seeds 11000–11079, unseen by both the search and its hold-out, against the full
pool: **12.35 → 13.00 points/sub-game, capture 75.0% → 79.8%, survival 80.0% → 92.0%.**

Two caveats belong with that number:

- **`barrier` got slightly worse** (8.12 → 7.88): our thief is still caught ~40% by a police that
  spends its quota freely, and every round traded a little of it away, because the objective is
  the *mean* over opponents and the mean was better served elsewhere. A min-max objective would
  choose differently. The league scores a mean, so the mean is right — but this is the known hole.
- **`mirror` moves with the incumbent**, so scores are only comparable *within* a run, never
  across rounds. The pool's other members are the fixed reference.

### The optimiser found a real exploit — in our own deception policy

Left free, the search set `lie_candidates` to **1**, which makes the thief's lie point at the
single furthest stale cell of a scent field *we transmit ourselves* — reproducing exactly the
decodable lie v4 had removed. It gained nothing measurable and risked everything.

The cause is worth more than the fix: **an optimiser tunes only what its objective can punish.**
Swapping the entire deception set between designed and searched values moves the result by 42–46
captures out of 80 — inside the noise — because only one pool member reads hints at all, and even
it never tries to *invert* a lie. So the deception fields are now listed in
`params.UNSEARCHABLE` and pinned at their designed values, with a test asserting a tuned file
naming them is ignored rather than obeyed. The honest long-term fix is a sparring partner that
exploits deception, not a tighter bound.

### What this still is not

It is simulation. §7's caution stands in full: the pool is a set of archetypes we wrote, and a
real team is not obliged to resemble any of them. That is exactly why `learn/clone_*` exists —
after a counted match, the sealed logs give the opponent's true position and move at every step,
and that team joins the pool as a fitted policy rather than a guess. **Until a counted match has
been played, the number to trust is "better against six archetypes on unseen seeds", not
"stronger in the league".**

## 9. v7 — a doctrine per physics, and the prediction it falsified

The league's shared conformance kit (`copthief-league-protocol`) registers **two** scent
models, and the one we did not implement is its CORE: `subtractive_chebyshev_v1`, the
reference implementation's physics. Flat Chebyshev rings 0.9 / 0.6 / 0.3 against our
figure-4 kernel, and decay by **subtracting** 0.1 rather than scaling by 0.9.

### The prediction, and why it was wrong

The reasoning going in was: a subtractive field is a short memory — an outer-ring cell dies
in three steps where ours still reads 0.2187 — and every trail-age reading in the doctrine
was calibrated on multiplicative traces, so playing it should cost us badly. `interop_uoh-sqak`
had already measured two thirds of our captures lost when the physics changed under a doctrine
that did not move with it, which made the inference feel safe.

It was backwards, and only measuring showed it. Hold-out seeds 9000–9011, full sparring pool,
league points per sub-game:

| doctrine ↓ / physics → | `book_v1` | `subtractive_chebyshev_v1` |
|---|---|---|
| `config/doctrine.json` (shipped) | **13.19** | 14.11 |
| `config/doctrine-subtractive.json` | 12.82 | **14.94** |

Even *before* any re-tuning, the shipped doctrine scored **higher** under the foreign physics
(14.11 vs 13.19). The flat rings are brighter and wider than our kernel's tail, so the police
reads the field far better — capture 77% → 93% — while the thief, emitting that same brighter
field, leaks more and survival falls 89% → 75%. The two effects do not cancel; the police gain
is larger, because the table pays 20 for a capture and 10 for a survival.

### What the search then bought

CEM over all 23 keys, 10 generations × 20 candidates, 12 training seeds, scored on 12 unseen
hold-out seeds and written only because the hold-out improved:

- **14.11 → 14.94 points/sub-game**
- capture **93% → 98%**, survival **75% → 92.5%** — the search recovered nearly all of the
  thief's loss without giving up the police's gain
- 15 of 23 keys moved. The thief half moved where the physics hurt it: `stay_penalty`
  0.053 → 0.580 and `corner_penalty` 0.243 → 0.513, i.e. under a field that betrays you
  brightly, standing still and hugging corners get much more expensive.

### The pairing is now the deliverable, not the file

Either doctrine loses 0.4–0.8 points under the other's physics, and **that loss is silent** —
nothing errors, the agent simply plays worse. So the model and the doctrine are one decision
in two variables (`P2P_SCENT_MODEL` + `P2P_DOCTRINE`), asserted together in
`tests/unit/test_doctrine_per_physics.py`, which also refuses any committed contract that
names the kit's physics without its doctrine.

The practical consequence for match-day: **if a kit-built team offers their CORE physics,
take it.** It is our best measured cell, +1.75 points/sub-game over playing at home.

§8's caveat applies unchanged and is worth repeating here, because this section is the more
tempting one to over-read: every number above is our archetypes playing our archetypes under a
different physics. It says the doctrine is better *at the game we simulated*. A kit-built
opponent is a real team, and the only evidence that settles it is a counted match.
