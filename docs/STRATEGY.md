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

Tuning lessons recorded for the README report: (1) always-on zigzag loses — straight flight is
fast, wander is slow; juke only when chased. (2) Claim frequency is an information price, not
free tempo — 0.15 beat 0.10 on fresh seeds 48:37. (3) Scent-trail velocity beats belief-peak
velocity as an interception signal (the belief peak jitters under hint noise).
