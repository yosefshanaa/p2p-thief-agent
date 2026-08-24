# Reply — ahk-yosi → MaRs-777 — 2026-08-24 (rev 2)

Mohamed, Rawey — four of your five asks are answered below with line references,
and one of them is a straight yes we did not have to build anything for.

The fifth is where we have to slow you down: **we believe your Step-0 will refuse
our greeting**, and if it does, no time we agree on today is real. That question
is at the top because it gates everything else.

Read at `b6b86053133a30a2a9280b5349a3d9db8b2b9a66`.

---

## FIRST — the one that can stop the friendly before move 1

**We do not send a Step-0 at all.**

We send an `identity` block **inside `negotiate`**. That is the only structured
description of ourselves that crosses this wire. Against your §3 shapes:

| your Step-0 member | what we actually put on the wire |
|---|---|
| `github_commits` object, both keys, `^[0-9a-f]{40}$` | `github_commit` **and** `git_commit_hash`, both **scalars** |
| `cpu_freq_ghz`, canonical decimal **text** | **absent.** Our spec block is os / machine / python / cpu_cores / ram_gb / gpu |
| `gpu`: non-empty string, or exactly `false` | the literal string `"none"` — passes your shape, and *means* a GPU named "none" |
| `vram_gb` omitted when no GPU | **absent** — correct, by accident rather than intent |
| `game_start`, `…T..:..:..Z` | **absent from the wire.** Our local declaration stamps `started_at` as `2026-08-24T18:20:00+00:00`, which your regex refuses |

You wrote two things that do not settle between them:

- "A scalar is refused at input validation — **before authentication**, before
  anything is read."
- "**The friendly needs none of this.** Only the result-agreement path calls
  `require_peer()`."

The second exempts us from *authentication*. It does not exempt us from *shape
validation*, which you place strictly earlier. So:

> **Does Step-0 shape validation run against a friendly greeting?**

- **If no** — we play today as agreed and add the fields at leisure.
- **If yes** — our greeting is refused at input validation, we never reach your
  role schedule, and this is the negotiate-shape incident again with the roles
  reversed. Then the fields have to land before we start, and you should tell us
  **now**, not at 18:40.

We are not guessing at it, because guessing is how we would ship the wrong five
fields.

---

## 1 — §10 enclosure: yes, and we did not have to build it

**Our thief already settles CAPTURE against itself, on both of your disjuncts,
unconditionally.**

`peer/turn_engine.py:61`, the first thing `build_own_step` does, before a move is
even computed:

```python
if self.role == THIEF and self.board.is_enclosed(self.own_pos):
    return {"event": self._captured_event("enclosed")}
```

`is_enclosed` is "all four orthogonal neighbours blocked — barrier **or board
edge**". The event seals `CAPTURE` to `POLICE` with cause `"enclosed"`.

Your other disjunct — standing on a blocked cell — is a separate terminal on our
side, rule #46, and also thief-side and also unconditional
(`peer/turn_engine.py:203`):

```python
if self.role == THIEF and barrier == self.own_pos:
    events.append(self._barrier_capture(barrier))
```

Three things you asked about specifically:

- **STAY is not an escape.** The check runs at the top of `build_own_step`,
  before `brain.decide` is called at all. There is no move, STAY included, that
  reaches the board with the thief still enclosed.
- **Neither of these reads `claim_enclosure`.** Only the pursuer-side emitter at
  line 67 does. So the flag you asked us to clear cannot silence our thief.
- **Our police-side emitter goes off.** `P2P_CLAIM_ENCLOSURE=false`, one config
  line, no code. Exactly one side reports it and it is yours.

Your BAR-004 reasoning is right and we arrived at the same place from the other
direction: our pursuer-side claim requires the *single* candidate cell to be both
open and enclosed before it will fire, precisely because a claim over a set of
candidates is a claim we cannot honestly make. Yours is the safer rule. We are
glad to drop ours.

So the rule-35 divergence you were worried about does not exist between us.
Confirmed in writing: **our thief implements GAME-005, on its own cell, in every
window, whatever the flag says.**

---

## 2 — the arithmetic: no, we do not recompute your grid. Not anywhere.

Confirmed, and here is the shape of the confirmation rather than an assurance.

Our audit module contains no `ScentField`, no `serve_for_step`, and no field
reconstruction of any kind. What our audit verifies is your **seals** — that each
revealed payload hashes to the commitment that preceded it — never your
arithmetic. A grid that hashes correctly is accepted whatever its digits.

Downstream, your published grid is consumed as evidence, not checked against an
expectation: it feeds `opp_tracker.observe` and `belief.scent_update`, both of
which read the values you sent. There is no branch anywhere that recomputes what
your field "should" have been and compares.

One disclosure in return, since you gave us yours. **We invert your served field
to infer your cell.** Your field has a unique structure around its source and we
read it. That is inference from what you publish, it is exactly the leak we warned
other teams about in our own physics, and it is not affected by Decimal-vs-float
at all — we read structure, never equality against a recomputed value.

And the mirror of your table: **ours is binary float.** You will receive
`0.7290000000000001` from us where your own field holds `0.729`. By your own rule
each side seals its own bytes and absorbs what it is told, so nothing breaks —
but you should expect the long tails, and if anything of yours ever compares a
received intensity for equality against a Decimal, that is where it will bite.

---

## 3 — §16: accepted as a requirement, and we found one more divergence first

Your causal chain is the argument. `_matches()` fails → `settle()` returns None →
no core, no `result_sha256`, no artifact, rule 35 zeroes both of us. That is not a
cosmetic row and we withdraw the suggestion that we run it mismatched.

**We are going to build it. We are not building it today, and here is the honest
reason:** your Step-0 answer above may change what we ship, and there is a second
divergence below that we would rather settle in this message than discover in an
artifact. Building an interop change against an ambiguous spec is how we would
spend the hour and still not match you.

### The divergence you have not accounted for: the tie award

Your §5 says `total_score` adds 2 to both sides when the series is tied, and is
therefore computed rather than summed.

**Ours sums the rows and never adds the award.** Our aggregate builder accumulates
each row's group-keyed score and derives `series_tie` from the totals; the 2 lives
elsewhere in our result document entirely. So a **tied series** would mismatch
between two implementations that are otherwise byte-identical — which is precisely
the case your own note predicts, and it turns out to be true of us specifically.

Everything else in your table we already match exactly: `roles` and `score` keyed
by group id, row `winner_group` null on a drawn row, `ties` counting the null
rows, aggregate `winner_group` null when totals are level. Those five aggregate
keys and five row keys are, key for key, the two tuples our `mutual_signature`
already uses.

Two questions so we implement the award once and correctly:

1. Is the +2 applied **only** when the series totals are level, or also on a
   drawn individual row?
2. Is it added to `total_score` **before** `winner_group` and `series_tie` are
   derived, or after? Adding 2 to both sides cannot change either, but if your
   code derives them from the awarded totals we want the same order.

### Envelope, confirmed

`sender` is the wire role in sub-game 6, and with us opening thief our g06 role is
**police** — same as your reading. Ours already sends the role the engine holds at
that moment, so this needs nothing.

### Our retry

Accepted. Our send is one attempt with the exception suppressed and no retry, and
you are right that it is your hazard mirrored. It goes in with the projection
flag, resending inside our 600 s linger until acknowledged. Same batch, same hour.

---

## 4 — D1: accepted, exactly as you describe

The proposer's timestamp, adopted verbatim, never reformatted or re-precisioned,
and a differing echo failing closed as `E-REPORT-DISAGREE`. That is the rule, we
will implement it that way, and we will implement the echo check too rather than
trusting our own formatter.

Thank you for treating the gap as a documentation debt rather than arguing it.
That is the second time in this exchange one of us has found a real hole by
reading rather than by playing, and it is cheaper every time.

---

## 5 — D2: understood, and we will send the object

`github_commits` as an object with **the same 40-hex twice**, once we ship the
Step-0 batch. Your input validation is right to demand the shape and we are not
going to argue for a scalar — our one-process topology is our business, and
making it invisible on your wire costs us one key.

The three sibling traps are noted, and `cpu_freq_ghz` as canonical decimal text is
the kind of thing we would have got wrong on the first try. We have been bitten by
the same class of bug from the other end: a wall-clock second inside a derived id
broke a mutual signature on every match until we found it.

---

## 6 — Q1: yes to the credential, for the counted game only

Mint it. `key_id` in clear in email; the secret by a channel you name that is not
this thread and not a chat window — a phone call or an out-of-band message either
way is fine, and we will confirm the fingerprint back to you before first use.

We note your §4.4: the friendly needs none of it, because only the
result-agreement path calls `require_peer()`. Good design, and it is why we can
still play today.

We have no authentication on our side of the wire at all — no tokens, no session
identity, nothing bound. So the credential will be entirely yours to define and we
will conform to it.

---

## 7 — §17, §18, §7: accepted, and one of them we are grateful for

**§17.** Noted, and thank you for correcting it unprompted. 1800 s across the
board puts you well above our 180 / 1000 / 600 and there is nothing for either of
us to raise. We would have planned around 30 s and 60 s and been wrong.

**§18.** Your answer is the reassuring one. `negotiate` reads the window number
off **our** greeting and your reply is bare `{"ok": true}` with no
`sub_game_number` in it — so there is nothing at your door for our forward-join to
misread, and the failure that cost us three runs cannot originate there. We are
still configuring you as a two-door peer with both doors on your one URL: the
guard costs nothing, the retarget is a no-op, and we would rather be protected by
construction than by your good behaviour.

Your bounded wait for window N−1 to actually settle is the other half of that
failure and we are glad it is there.

**§7.** Understood, and we appreciate you naming the seam rather than letting us
find it. A frozen contract that names your group, an override that would make
`is_frozen()` false, and a decision not to spend that detectability on one window
— that is the right call and we would have made the same one. Our concession
stands and we are not going to reopen it.

---

## SETTLED, BOTH DIRECTIONS

- **B1** `multiplicative_book_v1` @ `934c220d…` — closed.
- **B2** `setting: "Haifa"`, 14 of 14, `game_uid = 5ed16f3b-4e6b-4e9d-65bf-8f5abab699f2` — closed, reproduced independently on both sides.
- **B3** — closed, consequence accepted.
- **§13** — we open thief, you open police.
- **§10** — your thief-side GAME-005 owns it; our pursuer-side emitter goes off.
- **arithmetic** — neither side recomputes the other's grid.
- **B4** — costed after the friendly; the HMAC credential is the counted-only half.
- **§9, §11, §14, §15** and your AGREED WITHOUT CHANGE list — unchanged.

---

## THE FRIENDLY — **today**, not tomorrow

Our operator has moved it forward. Proposed:

**Today, 2026-08-24, 19:00 Israel (16:00 UTC).** Tunnels up 18:40, URLs confirmed
in writing, both sides probing until the 502/406 clears, start within a minute of
each other.

Two conditions, stated plainly rather than buried:

1. **The Step-0 answer at the top.** If shape validation gates a friendly
   greeting, 19:00 is not achievable and we should say so now rather than spend
   the slot on a refused handshake.
2. **§16 will not be fixed by 19:00.** You asked for the projection flag and the
   retry before the friendly and we are not going to promise an interop change
   inside three hours and have it be wrong. So if we play today, the friendly
   proves the transport, six windows of real play, the six mutual audits and the
   role schedule — and leaves settlement unproven, which you have told us is the
   half you most need.

That is your trade to make, and either answer is fine with us:

- **Play at 19:00 today** and take the transport proof now; we ship §16 straight
  after and prove settlement on a second friendly or on the counted run-up.
- **Hold** until §16 lands, and we name a slot once it is in and tested.

If you would rather hold, say so and nothing is lost. If 19:00 suits, answer the
Step-0 question and we will be up at 18:40.

Our endpoint is unchanged — one URL, both roles, reserved static domain, 502 from
the edge while we are down:

```
https://zealous-sliver-gleeful.ngrok-free.dev/mcp
```

— ahk-yosi (Ahmad & Yosef)
apexmediamind@gmail.com
`b6b86053133a30a2a9280b5349a3d9db8b2b9a66`
