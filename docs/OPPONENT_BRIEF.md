# OPPONENT BRIEF — what to send a new team, and what we must get back

One counted game per opponent, sealed forever once both reports are sent (book §9.2.1). So the
order is always: **exchange this brief → warm up uncounted (six sub-games) → play the counted one.**

Section 1 is copy-paste-ready to send. Section 2 is the reply we need. Section 3 is what we do
with their answers.

Questions 5–8 exist because of the `uoh-sqak` series (2026-08-09/10, `docs/interop_uoh-sqak.md`).
Each one is a defect that a healthy-looking short warm-up hides and that surfaces only at a
sub-game boundary or in the final audit — by which time, in a counted match, it is unrecoverable.

---

## 1. Message to send them

> **Team `ahk-yosi` (Yosef Shanaa 213314859, Ahmad Kaiss 325811255) — P2P Cops & Robbers match
> setup.** Repos: police https://github.com/yosefshanaa/p2p-police-agent, thief
> https://github.com/yosefshanaa/p2p-thief-agent. We'd like to play you, and to do it in the order
> that actually works: exchange contracts now, play a **full six-sub-game friendly** (uncounted,
> nothing filed or emailed), then the counted match — the book allows exactly one counted game per
> pair and it is sealed the moment both reports are sent, so anything that breaks at a sub-game
> boundary has to break in the friendly rather than in the real one. Attached is our constitution
> `game.json` (sha256 `3835f6a137620d8d98ab3925b2d1ed397d2d20d23bb9ba857bcd104284aac443`) — the
> book's defaults: 7×7, thief (3,3), cop (0,0), top-left origin index 0, 35 moves, 14 barriers,
> scoring 20/5/5/10/2, τ₀=0.9 ρ=0.10 5×5, 6 sub-games. Our handshake compares that hash by exact
> equality and refuses to start on any mismatch, so both sides must end up on a byte-identical
> file; send yours back if you want any value changed and we will adopt it (minimums may only
> rise). We speak both wire dialects — our own (`handshake` / `receive_commit` / `receive_reveal` /
> `audit_exchange`, request-response) and the course reference repo's (`negotiate` /
> `receive_turn` / `submit_audit` / `receive_control`, push-and-inbox) — so nothing needs to change
> on your side; just tell us which you run, and please send your **repo URL** so we can read your
> code rather than infer it (in our last setup a team's written brief disagreed with their own
> implementation on five values, and each one alone would have failed the handshake). What we need
> back:
>
> 1. Your `/mcp` endpoint and your repo URL. Any public tunnel works, but we run counted matches
>    over a **Cloudflare quick tunnel**: we measured ngrok's free tier dropping the MCP session
>    mid-sub-game with both peers healthy, where Cloudflare finished with `Verified OK` on both
>    sides. Free-tier URLs rotate on restart, so resend yours after any restart.
> 2. Dialect: reference / native / other.
> 3. Do roles alternate between sub-games? Do you re-negotiate before each sub-game, or handshake
>    once per series?
> 4. Enclosure (a thief with no legal move): does your **thief announce** it, does your **cop
>    claim** it, or is the rule off? Exactly one side may report it, or the series desynchronises.
> 5. **A commit golden vector** — one `payload`, one `nonce`, and the digest your code produces.
>    We will reproduce it byte-for-byte before the first move; if the two formulas differ, neither
>    side can audit the other and we would only discover it in the final audit.
> 6. Your scent physics as an **expression**, not prose: decay ρ, centre intensity, rounding, dust
>    floor, and whether a step is served the field **before or after** its own emission. One
>    number settles it (ours: τ₀=0.9 → 0.81 after one decay, served pre-emission). We are glad to
>    run yours — we keep a registered alternative and switch per opponent.
> 7. If your report carries a **mutual signature / shared result digest**: the exact function, its
>    JSON separators, and a golden vector — plus the exact strings you record for roles, results
>    and win claims. Whatever we send becomes the value inside your signed report, so a spelling
>    difference is a failed signature on both sides.
> 8. **Cold start**: we propose both peers begin at sub-game 1 at an agreed wall-clock time, and
>    that if indices ever disagree mid-series the peer that is behind **joins** the one ahead
>    instead of restarting. Two peers that both advance on failure and both insist on their own
>    index will livelock indefinitely, and it is invisible until it happens.
> 9. Your prior counted-game count (rule #37) — we declare **3** (orcai-mj, amireman/`G012`,
>    saedshki). Both declarations reach the lecturer, so they must be truthful.
> 10. First mover: we propose **thief** (book default), fine either way. Timeout: silence past
>     180 s forfeits that sub-game as a technical loss.
>
> At the end each team emails its own report to `rmisegal+uoh26finalgame@gmail.com`; a missing
> report forfeits that side's points. Send us a time for the friendly and a time for the counted
> match and we will be on the tunnel.

Attach `config/police/game.json` (both roles' files are byte-identical) and add the opponent's
team name at the top before sending. Send [`INTEROP_GUIDE.md`](INTEROP_GUIDE.md) with it — it
answers questions 5–7 from our side in full (commit formula, scent expression, mutual signature)
with golden vectors they can reproduce, so the reply we get back is usually just their numbers
against ours.

**If they build against [`copthief-league-protocol`](https://github.com/Imreec/copthief-league-protocol),
questions 5 and 7 are already answered.** We reproduce every CORE vector in that kit, pinned in
`tests/unit/test_kit_conformance.py`. Skip to the two it deliberately leaves per-pair — **which
scent model** and **who announces enclosure** — and ask only those. A kit-built team defaults to
`subtractive_chebyshev_v1`, which we can run but have never tuned against, so open by proposing
the book's `multiplicative_book_v1` (PROMOTED in their own registry).

---

## 2. The reply we need (checklist)

- [ ] Their `/mcp` URL **and their repo URL** — clone it; read the code, do not wait for
      attachments. Their prose is documentation and can be stale; their code is the contract.
- [ ] Dialect: native / reference / something else (we probe it too — see §3)
- [ ] Roles alternate: yes / no
- [ ] Re-handshake per sub-game: yes / no
- [ ] Enclosure (§3.4): who announces it — their thief / our cop / nobody
- [ ] **Commit golden vector**: payload + nonce + digest
- [ ] **Scent physics**: ρ, centre intensity, rounding, dust floor, serve order, one worked number
- [ ] **Mutual signature** (if any): function, separators, golden vector, and the exact vocabulary
      for roles / results / win claims
- [ ] **Cold-start time** and the index tie-break rule
- [ ] Their prior counted-game count
- [ ] Their `game.json` (or "we accept yours")
- [ ] First mover agreed
- [ ] Friendly time + counted-match time

## 3. What we do with it

**a. Probe the wire before believing the prose.**

```bash
PYTHONPATH=src .venv/bin/p2p-pursuit smoke https://their-url/mcp   # dialect=native|reference|unknown
```

The probe classifies their advertised tools, so the wire contract becomes a warm-up fact rather
than a mid-match surprise. **If the probe disagrees with what they told us, trust the probe** — a
wrong dialect means neither side can verify the other's commits at all.

**b. Reproduce their golden vectors before the first move.** A digest that is plausible but wrong
is indistinguishable from a correct one until a real opponent disagrees, and by then the sub-game
is already in the log.

```bash
uv run python -c "
from p2p_pursuit.domain.crypto import reference_commit
print(reference_commit({'a': 1}, 'ab' * 16))"   # substitute THEIR payload and nonce
```

Then pin theirs alongside ours in `tests/unit/test_reference_contract.py`, which already covers
the three places a wrong value hides: the commitment digest, the deterministic ids
(`reference_game_id` / `reference_game_uid`), and the mutual signature's *second* JSON encoding —
that one uses `json.dumps` **default** separators, not the compact ones the commit formula uses.
Four spellings inside the signed document (roles vocabulary, `result` values, `links` shape,
per-sub-game tie) are our reading of the reference family's prose; diff them against the new
opponent's kit before anything counted.

**c. Write their answers into a contract file** — never a constitution edit, which would ride
into the next team's handshake. No config surgery, no rebuild:

```bash
cp config/opponents/TEMPLATE.env config/opponents/<slug>.env
$EDITOR config/opponents/<slug>.env      # Q2/Q3/Q4 + dialect; keep P2P_EMAIL_MODE=draft
```

Warm-up (uncounted, six sub-games), then the counted match:

```bash
scripts/play.sh <slug> https://their-url/mcp --role thief --games 6
# then remove P2P_EMAIL_MODE=draft from the contract file and:
scripts/play.sh <slug> https://their-url/mcp --role thief --counted --prior-counted 3
```

`scripts/play.sh` loads the contract, picks a working runner, refuses an uncounted run that would
mail the lecturer, and makes a counted run confirm its recipient first. On a machine with `fish`,
`scripts/play.fish` is the equivalent.

**A doctrine belongs to a physics.** Adopting their scent model without swapping the doctrine
searched under it loses roughly two thirds of our captures — see `docs/interop_uoh-sqak.md` and
`docs/STRATEGY.md`. If their physics is one we have not met, run `p2p-pursuit learn` against it
before the friendly, not after. That is what the contract's `P2P_SCENT_MODEL` / `P2P_DOCTRINE`
pair is for: they move together or not at all.

**The counted run requires all six sub-games**, so a coordinated cold start (question 8) is a
precondition, not a nicety — joining at their mid-series index plays fewer than six, and
`--counted` refuses.

**`--prior-counted` is shared state across both machines.** It is **3** today (orcai-mj,
amireman/`G012`, saedshki) and rises by one per counted match. Rather than remembering it, read it
off the archive — whoever plays a counted match commits it to `matches/` immediately, and the next
number is the count of counted archives there. Two counted matches launching at the same time on
the two machines cannot each work it out: agree the two values in writing first
(README [§16](../README.md#16-match-record) keeps the running record).

**Watch the hash if you agree a term.** `P2P_MAP_AREA`, `P2P_HINT_MAX_WORDS`,
`P2P_MIN_CENTER_INTENSITY` and `P2P_AXIS_ORIGIN_CORNER` overlay the constitution *before* it is
hashed (`shared/config.py:206`), so setting any of them changes the `config_sha256` quoted in §1 —
e.g. `P2P_HINT_MAX_WORDS=12` moves it to `61068a97…`. Re-send the new hash, or the handshake
refuses on a value we ourselves advertised. Confirm what we will actually present with:

```bash
PYTHONPATH=src .venv/bin/python -c "from pathlib import Path; \
from p2p_pursuit.shared.config import load_shared; \
print(load_shared(Path('config/police/game.json')).sha256)"
```

Larger changes — board size, start cells, move budget, barrier quota, scoring, sub-game count —
are not env vars. Give that team a private `config/opponents/<slug>/{police,thief}/` and pass
`--config-dir`; editing `config/<role>/game.json` would ride into the next team's handshake.

Full operational detail — tunnels, the interop findings behind questions 2–8, scoring, and the
post-match archive step — is in `RUNBOOK.md` §1–4.
