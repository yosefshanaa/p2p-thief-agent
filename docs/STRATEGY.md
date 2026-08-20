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

---

## 10. v8 — reading the archive, and the estimator it condemned

Every version above tunes a policy. This one starts by asking a different question: **eighty-one
sealed sub-games have been played — five counted opponents, two more in friendlies, and the
reference peer — so what do they say we actually did wrong?** The answer is committed as a tool rather than quoted, so it can be re-run:

```
p2p-pursuit learn review          # read-only over matches/
```

Three findings, and the third invalidates a signal both brains were built on.

### 10.1 The police was not failing to find the thief. It was failing to convert.

A capture needs our cell to *become* the thief's cell, so a turn that begins with the thief one
orthogonal step away is a chance. Counting every one of them across the archive:

| what we did with a capture chance | turns |
| --- | ---: |
| **converted** — stepped onto it | **11** |
| spent the turn placing a barrier instead | 27 |
| stood still | 15 |
| walked somewhere else | 23 |
| **total chances** | **76** |

Fourteen per cent. And the largest single loss is self-inflicted: a barrier placement *forfeits
the move*, so more than a third of all chances were traded for a wall from a cell adjacent to the
thief. Alongside that, 157 barriers bought 287 turns in which the police could not reach the
thief **at all** — behind its own walls.

### 10.2 The thief was walking into the pursuer's reach

Across 35 thief sub-games it finished its move inside the cells the pursuer could take next on
**43 turns**, and was captured on 14. The deaths are not spread evenly: 79% of them are on the
bottom or right edge, which is the signature of the third finding.

### 10.3 The position estimate was a scan artefact

Both brains read the opponent's cell off `max()` of its served scent field. That field
**saturates**: emission *adds* the book's kernel and clamps at 0.9, so after a handful of steps a
whole swathe of cells sits at the cap. Measured over every sealed record — 91% of served fields
have between 6 and 20 cells tied at the maximum, and one has 20. `max()` then returns whichever
tied cell row-major iteration reaches first, which is a bias toward the **top-left**.

Replayed against the ground truth in the same records, that estimator names the emitter's cell
**219 times in 1,935** — 11%. And a thief weighting a top-left phantom at `w_trail` runs
south-east, which is exactly where 11 of its 14 deaths are.

Worse, it was switched off entirely for most matches anyway. The v7 search had set
`police_fresh_min` to **0.849** — above the **0.81** ceiling `book_v1` can physically serve, since
it serves the field *before* the step's own emission. Instrumented in the lab, the police's trail
branch fired **0 times in 2,629 turns**. `thief_fresh_min` was 0.850, the same story. The search
could not see the problem because an objective cannot punish a feature that never fires; both
bounds are now capped at 0.80, which repairs every committed vector on load.

### 10.4 The field is not weakly informative — it is fully invertible

One step of the scent model is a known function of exactly one unknown: the emitter's cell. So
solve it. `domain/scent_locate.py` replays `ScentField` forward from the previously served field
for each of the 49 candidate centres and keeps the one that reproduces the field we received.
Replaying the model itself, rather than re-deriving any algebra, makes this **model-agnostic** —
whichever physics a match negotiated is the physics that gets inverted, serve order, rounding,
clamping and all.

Against the archive: **1,935 of 1,935 transitions, exactly.** Against 11% for the estimator it
replaces.

What differs between the three registered models is only the *lag*. `book_v1` serves before
emitting, so a fix names where the opponent stood one step ago — and since the thief moves first
each round, that leaves the police a five-cell answer. `registered_v3` and
`subtractive_chebyshev_v1` serve after, so the fix is the opponent's cell *now*.

This cuts both ways and it is worth saying plainly: **our own position is equally readable**, by
anyone who does this arithmetic. Under `subtractive_chebyshev_v1` it does not even need
arithmetic — the argmax alone is exact, which is how gal-roy1 dropped a barrier on our thief. The
consequence for doctrine is that a thief cannot hide; it can only keep geometry. Deception, in
this league, is a tax on opponents who do not invert the field.

### 10.5 What changed in the two brains

**Police** (`v6`): order of business is now **pounce → squeeze → barrier → pursue**.

- The *pounce* steps onto a cell that is plausibly the thief's, in preference to barring it.
  Landing-and-claiming is answered under rule #21, which every peer implements because the
  protocol does not work without it; rule #46 (a barrier onto the thief) is optional and several
  peers we have played ignore it. Same evidence, same trigger — but one keeps the move and is
  settled by a rule that is actually agreed.
- `pounce_floor` gates it on the probability the fix implies, because under `book_v1` five cells
  share the mass and "chase the likeliest cell every turn" measured *worse* than not pouncing.
- `w_cut` scores the ground we take from the thief (a Voronoi split), not just the distance we
  close. Pure distance is a tail chase between equal-speed agents: the evidence names where it
  *was*, so aiming there holds the gap open forever. The counted match against gal-roy1 is the
  clean example — over 102 police turns the gap sat at **2 for 45 of them** and reached 1 only 3
  times, the thief was never once within a single step at our decision, and 27 barriers bought
  **zero** capture chances.
- The barrier branch no longer fires on the belief peak while a fix is in hand. The pounce has
  already declined every cell we can reach, so a placement there goes on ground the tracker says
  the thief is *not* on — it cannot convert under rule #46 and it forfeits the move anyway. Lab
  effect is small (0.77 → 0.70 barriers/sub-game, capture unchanged) because the lab barely
  spends barriers; the archive spends **3.4 per sub-game**, which is where it is aimed.
- Sealing a pocket is now refused unless the thief could be *in* it, which is what the 287
  cut-off turns were.
- The enclosure claim (`turn_engine`) no longer names its cell by that argmax. It was a sealed,
  audited claim resting on an 11%-accurate estimate.

**Thief** (`v6`): the pursuer's cell is now known, and one new term follows from it.

- `w_strike` penalises ending the move inside the pursuer's next-step reach — the 43 exposures.
- The same map answers a second question for free: the cells a pursuer can *bar* are exactly the
  cells it can step onto, so multiplying the strike values of our exits gives the chance it can
  seal us in. That term is gated on `claim_enclosure`, because where the rule was **not** agreed
  a sealed pocket is a *survival* — that is how the reference peer beat us on 2026-08-01, sitting
  in one for 27 turns while our police finished outside its own wall.

### 10.6 A third way to model an opponent

The pool had two: a fitted linear clone (about three moves in four) and a fixed script (honest
only for a deterministic opponent — of eight teams, only gal-roy1's thief and s82kma9e's police
qualify). Neither fits a *reactive* team, and reactive is what most of them are.

`learn/recorded.py` keeps every observed decision and replays the move the team played from the
nearest state we ever saw them in. `p2p-pursuit learn record --name <team> --match <dir>...`
builds one from the sealed logs, reporting agreement on a held-out quarter of the decisions:

| team | as police | as thief |
| --- | ---: | ---: |
| reference | 95% | 99% |
| orcai-mj | 87% | 100% |
| amireman | 80% | 72% |
| gal-roy1 | 50% | 100% |
| saedshki | 42% | 100% |

They join the pool as `recorded:<team>` in the roles they were actually observed in.

### 10.7 The objective had a hole in it, and it was not in the search

The v8 thief search returned **9.941 → 9.971 points** — nothing. Not because the thief is
optimal, but because sixteen of seventeen pool members scored a flat **10.00** against it. An
objective that cannot distinguish two thieves cannot improve one, and this one duly spent its
freedom driving `corner_penalty` to **0.001** — it had never been shown a pursuer that could
punish a corner. That is the same failure mode as §8's deception keys, and it deserves the same
answer: fix the sparring, not the bound.

Two holes, both found by asking why the lab and the wire disagreed. The archive says our thief is
caught in **14 of 35** sub-games; the lab said 1 in 100.

**The lab was not playing the league's rules.** Whether the police issues a capture claim every
turn is negotiated per opponent — amireman and gal-roy1 signed `always_claim`, s82kma9e did not —
and the lab defaulted to *off* for both sides. With it off, a pool police can only convert by
barrier or by enclosure, because `BrainBase.should_claim` wants belief ≥ 0.5 and the measured
posterior peak never reaches it. So the objective had quietly deleted the police's main
conversion path. Both regimes are now played, **split by seed** so the cost does not double and
`claim_threshold` stays searchable. Thief survival against the pool: **94.0% → 86.6%**, and half
the pool acquires a way to punish a mistake.

**No pool member knew where the thief was.** Every police archetype navigated by belief or by the
field's argmax — i.e. by the estimator §10.3 condemned. `interceptor` is the opponent that does
what we now do: invert the field, chase the exact cell, and close doors. Adding it is a hedge
with a clear rationale — the inversion is arithmetic over a field the rules *require* both peers
to publish, so a doctrine that only survives opponents who have not noticed has an expiry date.

Building it produced a result worth recording on its own: **a pursuer that knows the thief's exact
cell and simply walks at it catches our evader 0 times in 12.** Two equal-speed agents on open
ground never meet. Captures come from taking the room away — which is why `interceptor` cuts
territory and spends barriers, and why our own police grew `w_cut`.

### 10.8 What the thief got that tuning could not have given it

Because the search had so little to say about the thief half, its two real improvements are
structural and evidence-led rather than fitted:

- **`w_strike`** — do not end the move inside the pursuer's next-step reach. 43 archived turns did
  exactly that; 14 of them ended the sub-game.
- **Escape room** — the territory term now counts only cells reachable *without walking through*
  the pursuer's reach. A plain Voronoi count walks straight through it, which is why an edge run
  into a corner scored as roomy until the last turn, and why 79% of this thief's deaths are on
  the bottom or right edge. On the exact board from the counted match against gal-roy1, the thief
  now breaks off the edge at (1,6) instead of stepping into (0,6) where it was barred in.

The honest limit: the arena still overstates our thief badly (87% survival against 60% on the
wire), so the thief half of v8 rests on the archive, not on the search.

### 10.9 Result

Four co-evolution stages, each hold-out gated on seeds its search never saw, each starting from
the previous stage's file so that `mirror` — ourselves — is the *improved* opponent rather than a
fixed target:

| stage | points | capture | survival |
| --- | --- | --- | --- |
| police, round 1 | 15.74 → **19.21** | 71.6% → **94.7%** | — |
| thief, round a | 9.51 → **9.91** | — | 90.3% → **98.2%** |
| police, round b | 18.42 → **18.75** | 89.5% → **91.7%** | — |
| thief, round b | 9.77 → **10.00** | — | 95.4% → **100%** |

Each baseline *falls* as the other role improves — round b's police starts at 18.42 where round a
ended at 19.21, because it now faces the round-a thief. That is the co-evolution doing its job,
and it is why a single-round search overstates itself.

The thief half is the more interesting record, because the search reinforced the new term twice
without being asked to: `w_strike` went 4.0 (designed) → **4.79** → **8.13**, and `corner_penalty`
climbed back from the 0.001 the blind objective had left it at to **0.244**.

**End to end**, v5 agent against v8 agent on a fresh validation range (seeds 21000–21015, 22
opponents, both claim regimes):

| | points/sub-game | capture | survival |
| --- | ---: | ---: | ---: |
| v5 doctrine + v5 estimator | 11.791 | 58.9% | 92.7% |
| **v8 doctrine + v8 tracker** | **14.071** | **86.8%** | **97.9%** |

And the archive's own conversion metric, measured in the lab under the same definition:

```
v5:  377 chances, 147 converted (39.0%),  88 lost to a barrier,  3.89 barriers/sub-game
v8:  876 chances, 178 converted (20.3%),  29 lost to a barrier,  0.75 barriers/sub-game
```

The v8 police creates **2.3× as many chances** — it can find the thief now — and spends **five
times fewer barriers**. Its conversion *rate* is lower, and that is not a defect: under a lagged
fix most of those extra chances are a one-in-five gamble that `pounce_floor` correctly declines
in favour of position. The outcome, 58.9% → 86.8%, is what the table pays for.

### 10.10 What is honest to claim, and what is not

- **`w_cut` is narrow.** On the full mixed pool it scores identically to zero (14.037 either way).
  Against the partners built from real teams it is a real optimum — 80% → **92.5%** capture at the
  tuned 0.074, falling back to 80% at 0.0 and at 0.5. Its case rests on those and on the archive,
  not on the aggregate.
- **One partner regressed**: `recorded:orcai-mj`, 15.00 → 7.50. It is an **11-state** table — their
  thief sub-games ran 12 steps because we captured them quickly — so it has almost no coverage and
  behaves arbitrarily once our police plays differently. The linear clone of the same team went
  *up* over the same seeds. Thin partners are noise, not evidence.
- **The arena still overstates the thief.** 97.9% survival here against **60%** on the wire (14
  captures in 35 archived sub-games). The thief half of v8 therefore rests on the archive
  findings and on terms whose reasoning is checkable, not on the search's own delta.
- **None of this is a counted match.** Every number above is simulation. The only evidence that
  settles it is a league game.

### 10.11 The pairing, re-measured under v8

Both vectors re-searched from scratch (both roles, 28 keys, hold-out gated), then each played
under each physics on validation seeds 18000-18009 against the full 22-opponent pool:

| | `doctrine.json` | `doctrine-subtractive.json` |
| --- | ---: | ---: |
| **book_v1** | **14.081** | 13.905 |
| **subtractive_chebyshev_v1** | 14.270 | **15.095** |

The diagonal still wins, and §9's match-day advice is unchanged: **if a kit-built team offers
their CORE physics, take it** — 15.095 is the best cell on the board.

The off-diagonal is the more instructive number. Playing the *book* vector under subtractive
physics still captures **100%** — the police is fine — while thief survival collapses to
**64.4%** against 98.3%. Nothing errors; one half of the agent simply plays a game it was not
tuned for. That is the whole argument for `P2P_SCENT_MODEL` and `P2P_DOCTRINE` being one decision
in two variables.

All 28 keys differ between the two vectors, and the differences read as physics rather than as
noise: subtractive serves *after* emitting, so its fix names the pursuer's cell **now** rather
than one step ago, and the search spends that precision — `corner_penalty` 0.244 → **0.409**,
`w_strike` 8.13 → **9.14**, `w_cut` 0.074 → **0.544** — while zeroing the hedges that only ever
stood in for uncertainty: `stay_penalty`, `w_territory` and `w_trap` all go to 0.

### 10.12 A third vector, and the pattern the three of them make

`registered_v3` re-searched the same way: **14.651 -> 15.045** points, thief survival
**80.1% -> 96.3%**, capture already at 100%. Twenty-five of 28 keys differ from the book vector.

Both of the models that serve *after* emitting behave the same way, and it is the lag that
explains it. Under `book_v1` a fix is one step old, so the thief could be on any of five cells;
under the other two it is the opponent's cell **now**. Exact information is worth weighting, and
the search weights it — without being told which model it is looking at:

| key | `book_v1` (lag 1) | `subtractive` (lag 0) | `registered_v3` (lag 0) |
| --- | ---: | ---: | ---: |
| `w_cut` — take ground, not distance | 0.074 | **0.544** | **0.458** |
| `w_strike` — never end inside its reach | 8.13 | **9.14** | **9.00** |

Both lag-0 vectors also put the police at **100% capture**, so every point the search found there
came from the thief half. That is the mirror of the same fact: a physics that hands *us* the
opponent's exact cell hands them ours, and the evader is the side that pays.

They diverge elsewhere, which is the argument against treating "lag 0" as one physics:
`corner_penalty` goes **up** under subtractive (0.409) and **down** under registered_v3 (0.140),
because a flat Chebyshev ring and the book's radial kernel corner an evader differently. Three
models, three vectors, and `P2P_SCENT_MODEL` picks which.

### 10.13 The per-opponent pairing, and one term that did not survive contact

`config/doctrine-orcai-mj.json` — the vector `amireman.env` and `friendly-0812.env` both point at
— re-searched against a pool weighted toward those two teams: **13.553 -> 14.320** points,
capture **78.3% -> 90.0%**, at a cost of **100% -> 93.5%** thief survival. The search traded a
little evasion for a lot of conversion, which is the right trade at 20 points a capture against
10 for surviving, and it is the trade the objective is built to find.

Four vectors now ship, and the numbers that produced each are above:

| file | physics | hold-out |
| --- | --- | --- |
| `doctrine.json` | `book_v1` | four co-evolution rounds, §10.9 |
| `doctrine-subtractive.json` | `subtractive_chebyshev_v1` | 14.313 -> **15.113** |
| `doctrine-registered_v3.json` | `registered_v3` | 14.651 -> **15.045** |
| `doctrine-orcai-mj.json` | `book_v1`, their pool | 13.553 -> **14.320** |

### 10.14 Re-deciding the archive, and the four candidates that failed the test

§10.1 counts what the doctrine of the day *played*. It has been quoted since as a live defect,
which it no longer is: those logs were recorded before `_pounce` existed. `learn/counterfactual.py`
asks the other question — standing in exactly the state the archive records, what does *this*
vector do? The opponent's served field is not archived, but a served field is a pure function of
the trajectory that emitted it, so it rebuilds; checked against the fields the archive *does*
store — our own — the reconstruction is bit-identical on **2429 of 2429**, across all three
physics. Same 76 chances, re-decided:

| what we do with a capture chance | as played | today |
| --- | ---: | ---: |
| **converted** — stepped onto it | **11** | **26** |
| barred the thief's own cell (rule #46) | 0 | 7 |
| spent the turn placing a barrier instead | 27 | **0** |
| stood still | 15 | **0** |
| walked somewhere else | 23 | 43 |

Both self-inflicted losses are gone outright. What remains is a lagged fix genuinely too thin to
bet a turn on — under `book_v1` the fix is one step old, so five cells share the mass — and the
obvious remedy does not work. **`pounce_floor` gates an early return**, so lowering it does not
take more shots, it stops `_pursue` running at all and takes the territory, anti-camp,
anti-dither and mixing rules with it:

| `pounce_floor` | archive conversions | lab capture rate |
| ---: | ---: | ---: |
| 0.262 (shipped) | 29 / 76 | **0.812** |
| 0.20 | 29 / 76 | 0.704 |
| 0.15 | 29 / 76 | 0.704 |
| 0.10 | 35 / 76 | 0.604 |
| 0.04 | 35 / 76 | 0.567 |

Every row is the shipped vector with one key moved, so the table is one series and not a splice.
Buying six conversions costs twenty points of capture rate, which is not a trade worth making.

So the evidence is priced as a term instead. **`w_pounce`** scores a candidate cell by the mass
the tracker puts on it, on the same scale as distance — one unit means "a cell that certainly
holds the thief is worth one step of ground", which is a tie-break, which is all a sub-threshold
chance should ever be. It takes the archive to **29 / 76** and won on **five independent seed
sets**, none of them used to choose it:

| seeds | capture, `w_pounce` 0 | capture, `w_pounce` 1 |
| --- | ---: | ---: |
| 30000–30030 | 0.779 | **0.812** |
| 31000–31040 | 0.784 | **0.791** |
| 32000–32040 | 0.762 | **0.784** |
| 34000–34120 | 0.772 | **0.794** |
| 37000–37080 | 0.770 | **0.800** |

Pooled, +0.023 over 2480 police sub-games — about two standard errors, so: real, and small. It is
an exact **no-op under any lag-0 physics** (`subtractive_chebyshev_v1`, `registered_v3`), where
`_where` is a delta on the fix and the pounce has either spent it or cannot reach it — measured
identical to three decimals over 640 sub-games. The physics we prefer to negotiate carries no
risk from it at all.

**Four candidates were measured here and rejected.** They are recorded because each is the kind of
thing that reads as an obvious fix and would otherwise be proposed again.

*`flee_bias` is genuinely miscalibrated, and correcting it makes play worse.* `predict.spread` is
a likelihood, so every observed opponent step is a labelled sample and the weight can be fitted
rather than assumed. Fitted over 636 real-team steps it is **1.05**; we ship 2.76. The value we
ship is what the **reference kit's own bot** fits (3.90) — every actual league team we have played
fits 1.00–1.15 — so it was calibrated against a bot, not an opponent. And it does not matter:
at the fitted value the archive converts **no additional chance** — 29 / 76 either way — and the
lab loses nine points of capture (0.812 → 0.725). The weight is doing a pursuit job — lead the quarry — not a forecasting
one, and one-step predictive accuracy is the wrong objective for it. Same result on the thief's
mirror key, `chase_bias`: fitted 0.90 against the 0.20 `doctrine.json` actually carries, and
marginally *negative* in play (survival 0.906 → 0.897).

*Turning the kill shot into a step measured worse.* Rule #21 is honoured by every peer; rule #46
is not, so barring a cell we could step onto looks like trading the agreed conversion path for the
unagreed one. It scored 0.784 → 0.775, and on inspection the patch had barely fired: the kill shot
is belief-gated, and an archive replay has no belief to feed it. **Belief-gated branches cannot be
judged from the archive at all** — that limitation is now in `counterfactual`'s docstring, because
a null result from the wrong instrument is worse than no result.

*A barrier on the police's own cell is not reachable.* `validate` permits it (`cell != pos` is the
guard) and `safe_decision` does not catch it, so it would bar the ground we stand on. It occurs
**0 times in 15,818 lab turns** across both physics: `still_connected` vetoes it, because it
cannot path from a source cell it has just barred. Incidental rather than explicit, but real.

