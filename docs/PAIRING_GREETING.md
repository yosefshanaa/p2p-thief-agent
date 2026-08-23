# Pairing greeting — team `ahk-yosi` — rev 2026-08-23

Hi — we're **ahk-yosi** and we'd like to play a series against you: one uncounted
friendly first, so both sides' artifacts reconcile byte-for-byte, then the counted
series. Everything below is copied out of running code in our repo, not from
notes, and every hash in it is reproducible on your side.

We have played **seven** counted series (orcai-mj, amireman/G012, saedshki,
s82kma9e, gal-roy1, uoh-ay26, najamjad) plus friendlies against najamjad,
vibecode and uoh-sqak. The book allows exactly **one counted game per pair**,
sealed the moment both reports are sent, and the cap is 10 — so we have three
slots left and a counted series with you would be one of our last three. That is
also why we want the friendly first: anything that breaks at a sub-game boundary
has to break there, not in the one game that counts.

---

## FIVE ASKS UP FRONT

### 1. Your `group_id`

The exact identifier, lowercase, no spaces, as it goes on the wire. It is the
first signed key of the `game_id`, so nothing can be pre-derived without it.

Ours is: **`ahk-yosi`**

### 2. The scent model — and please recompute the hash rather than trusting ours

We would like:

```
subtractive_chebyshev_v1
81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4
```

Both sides declare the digest at Step-0 and declared-and-different aborts before
move one. We also support:

```
registered_v3   0761ca169ee93a11cb19e6e28251074ab7223bdb157ec5123138d87aad651f6f
book_v1         ea7225f5d71989add99a0057287342b7c5b86ab4efffd1608da25d0e368c0a28
```

**One warning about `book_v1`, because it has cost a pairing an entire evening.**
"book_v1" is not one document. Our book digest is `ea7225f5…`; the kit's
registered book document hashes to `934c220d…`. If your book doc is the kit's and
ours is ours, a book series refuses at the handshake on the scent lock even
though both sides typed the same model name. Both of us adopting the kit's
**subtractive** document byte-for-byte is the one path where the two digests are
identical by construction. That is the real reason we ask for chebyshev — not
preference.

### 3. Which side of the decay you cut the transmitted packet from

This is the most expensive ambiguity we have found, and **it is invisible to the
hash.** The lock document pins `deposit_then_decay` for the *grid* and never says
whether the transmitted packet is cut before or after the decay step. Both
readings hash to `81ebee59…`, so the digest cannot separate them — only a
sentence in writing can.

We measured both branches on our own field this morning:

| cut | freshest centre | next ring | outer ring |
|---|---|---|---|
| **before** decay | 0.9 | 0.6 | 0.3 |
| **after** decay | 0.8 | 0.5 | 0.2 |

An opponent who decodes intensity as age and guesses wrong is handed a
systematic one-step lag on every single turn. We have played it both ways
(najamjad reads it early, s82kma9e's published golden fields require the late
one) and we will conform to either. We just need the word, per-series, in
writing. **Tell us which one you serve and we will match it.**

### 4. Your commit golden vector

One `payload`, one `nonce`, and the digest your code produces for them. We will
reproduce it byte-for-byte before the first move.

This matters because there are two live spellings of the commitment and we
support both, selectable per match:

```
reference:  sha256( canonical_json(payload) + "|" + nonce )     # nonce outside the JSON
native:     sha256( canonical_json(payload including the nonce) )
```

`canonical_json` here means sorted keys, separators `(",", ":")`, UTF-8, no
ASCII escaping. If the two formulas differ and nobody checks, neither side can
audit the other and you find out in the final audit, with the series already
played. One vector each way settles it in a minute.

Ours, on request, in the same form.

### 5. A stable endpoint — and the same honesty in return

Please send a fixed hostname: static IP, named tunnel, anything that survives a
restart.

**In fairness: our public URLs are Cloudflare quick-tunnel hostnames today and
they rotate on every restart.** So we re-send ours in writing immediately before
each run and never assume a previously-sent URL still resolves. If you need a
stable hostname from us for scheduling, say so and we will stand up a named
tunnel before T.

One measured recommendation on the transport: we run counted matches over
**Cloudflare**, not ngrok. We watched ngrok's free tier drop the MCP session
mid-sub-game with both peers healthy, where Cloudflare finished with
`Verified OK` on both sides.

---

## OUR TOPOLOGY — please read this one; it is where peers most often mis-dial us

**We run ONE process on ONE port**, holding one role at a time and swapping at
each window boundary. **We are not two agents.** Our two GitHub repos are a
submission split of one role-configurable codebase, not two running peers.

What that means for you: **give us one URL and point both roles at it.** If your
client retargets per role (a `{role}` template, or separate cop/thief doors),
point both entries at the same hostname so your retarget is a no-op. A peer that
dials a different door for our cop than for our thief finds nothing on half the
windows.

We state this plainly because we once told an opponent the opposite — we inferred
"two processes" from our own port-naming convention and it was false. If our
topology is a settlement issue for you, say so now rather than at T; we would
rather lose the pairing than have you discover it in window 2.

Corollary you will see in our artifacts: our per-window `github_commit` is one
value on all six rows, because there is one working directory. That is expected,
not drift.

---

## THE HANDSHAKE SURFACE

We serve **both** tool sets on the same port, so whichever dialect you speak, you
will find us:

```
reference-v3:  negotiate(message)      receive_turn(message)
               submit_audit(payload)   receive_control(message)

native:        handshake(payload)      receive_commit(msg)
               receive_reveal(pub)     receive_event(envelope)
               audit_exchange(package) get_status()   health_check()
```

Extra tools and extra properties on your arguments are fine — we accept
supersets. Tell us which dialect you speak and we will set ours to match. Our
code default is `native`; every recent series has run `reference`.

If you are on the reference dialect, when you probe our tunnel you must see
**both** tool sets in `tools/list`. If you only see one, our peer is not fully up
yet — wait, do not reconfigure.

---

## THE 14 SIGNED TERMS — the only thing that has to match

A closed, flat, 14-key agreement sent at Step-0. Ours, canonical, so you can diff
it as one string rather than eyeballing a table:

```json
{"axis_origin_corner":"top-left","axis_start_index":0,"barriers_max":14,"board_size":7,"cop_start":[0,0],"decay_per_step":0.1,"emit_intensity":0.9,"hint_max_words":15,"max_steps":35,"min_center_intensity":0.5,"num_games":6,"setting":"New York","smell_grid_size":5,"thief_start":[3,3]}
```

Note what is **not** a wire term: `survival_threshold`, `response_timeout_sec`,
`watchdog_timeout_sec` and the token budget are operational values in our repo
config. Diff the 14 above and ignore the rest.

**`config_sha256`** is `sha256(canonical_json(your own repo-local game.json))`.
It goes into the declaration; we do **not** refuse on it, and you should expect
ours and yours to differ — `agreed_between` names the pairing and is inside the
hashed object, so the value is per-pairing by construction. Ours is
`a7933121447441e1c7bca2962ce92e26374f1b5eb62355d441b9b0aa7a40e7f8` today and
will change the moment we set `agreed_between: ["ahk-yosi", "<you>"]`.

Our `schema_version` is **1.2**.

**One term-signing subtlety, for the friendly.** If we agree to a short
compatibility run — say two windows instead of six — the signed `num_games` must
still say **6**. Signing the short count fails the peer's terms comparison on the
very run meant to prove the terms agree.

---

## `game_id` AND `game_uid` — settle this before any T

`game_uid` derives from the terms plus the team pair, so **every series between
the same two teams collapses to one uid** unless a per-series label is folded in.
Agree in writing, before the first window, on exactly one of:

- `label <NAME>` — both sides derive it and cross-check the labelled uid in chat
  before T; or
- `unlabelled` — explicitly.

A one-sided label is refused at the handshake and the window is lost. We have
watched exactly that happen.

Also agree the **shape** of `game_id`. Some peers derive `"<lo>-vs-<hi>"` from the
sorted pair with no label slot at all; if that is you, we must both leave the
label unset — and unset means **omitted**, not empty string. `game_id` is the
first signed key of `mutual_agreement.sha256`, so a label on one side only
guarantees a digest mismatch at the end of an otherwise clean series.

One more, and it is ours to confess: our `game_id` must be **derived from the
pair, never stamped with a wall-clock timestamp.** We had a bug that put the
current second into it, which breaks the mutual signature on every native match.
Fixed — but if you ever see a timestamp inside a `game_id` from anyone, that is
the bug.

---

## TURN ORDER, ROLE ALTERNATION, AND WHO OPENS AS COP

**Thief moves first in every sub-game.** That is in our terms
(`first_mover: thief`) and is not negotiable on our side.

**Role alternation is a negotiated flag, not a league rule.** In our code it
defaults to **off**; we turn it on per opponent. When it is on, the rule we
implement is: *the role a peer launched with on odd sub-games, the other role on
even ones* — so window 1 decides the whole schedule. Getting this wrong voids a
match from sub-game 2 onward while sub-game 1 looks perfect, which is exactly how
a one-window warm-up passes and a six-window counted match dies.

**We launch as cop.** Police is our scoring half — a capture pays 20 where a
survival pays 10 — so we launch `--role police` and hold cop on windows 1/3/5.

Two honest caveats, because we would rather you hear them now:

- Some teams propose parity from the sorted pair of group ids ("the group sorting
  first cops the odd windows"). That is a convention two peers can adopt, not
  something our code derives — we derive it from the launch role. If you want the
  sorted-pair convention, say so and we will launch to match it.
- We **cannot promise to force cop**, and we will not pretend otherwise. If your
  peer claims the role we computed, ours takes the complementary one rather than
  forfeit — forfeiting is a technical loss. So their claim gets the last word. The
  role is settled while `my_steps == 0`, before any turn, and nothing is filed at
  zero turns; if we read the join line and it says thief, we kill the peer and
  relaunch inverted. That costs about three minutes and no artifacts.

So the only thing we need from you here is one sentence: **which role does your
peer open window 1 with?** If we both say cop, one of us relaunches before T
rather than colliding at it.

---

## COMMIT-REVEAL, THE PUBLIC PROJECTION, AND CAPTURE

Every step is sealed with a **fresh nonce**. The sealed record carries the step
index, the role, the sub-game (under both spellings), both positions, the move,
any barrier, the intent, the hint and the served scent field. Nonces stay secret
until the sub-game audit.

The **per-step reveal discloses only the public projection**: hint, served
smell_grid, barrier declaration. Move, both positions and intent stay sealed
until the audit — a per-step move reveal would collapse the partial-observability
premise the whole book is built on. Note that the public fields are inside the
*same* commitment as the private ones, so nothing can be retro-fitted at audit
time either way.

The hint is free text, at most 15 words, and is not binding.

### Capture claims — please pick, and here is our measurement

- **(a) `always_claim`** — the cop attaches `capture_claim = its own cell` to
  every turn.
- **(b) threshold** — the cop claims only when its own belief justifies it.

**We ask for (b), and we would rather explain why than just assert it.** A claim
names a cell, and answering one collapses the answering side's belief to a delta
on exactly that cell — which is the claimant's own position. So a cop that claims
every turn broadcasts its location every turn. Measured against a hold-out evader
over 100 seeds, our own police capture rate:

```
book_v1                   always_claim=false  35%   ->   always_claim=true   0%
subtractive_chebyshev_v1  always_claim=false  21%   ->   always_claim=true  23%
```

Under `book_v1` it is the whole leak, and it is not hypothetical: the one counted
series we played on book with `always_claim` on converted 0 of 3. Under
subtractive it costs nothing, because a thief can invert our served field anyway.
So: **on subtractive, either is genuinely fine with us. On book, we ask for
threshold.** Every contract we currently ship is threshold.

Either way we answer your claims honestly, from our true position, with:

```json
"claim_response": {"claim": [row, col], "caught": true}
```

echoing the asked cell verbatim. `caught: true` is terminal.

### Enclosure (rules 46/47) — please state your position

Some peers want the **thief** to concede when a barrier lands on its cell or it
has no legal move; others want the **cop** to claim the enclosure. Exactly one
side may report it, or the series desynchronises.

This is not cosmetic. A capture the thief never acknowledges is a rules 33–35
void for *both* teams, which is strictly worse for the claimant than the survival
they declined.

Our code default is **cop-claims-enclosure ON**. Against najamjad we agreed to
turn it **off**, on their reasoning — rule 47 wants the thief's confirmation, and
their thief concedes on its own turn, so waiting costs us nothing. We will play
it either way. We need one sentence.

---

## `mutual_agreement.confirmed` — the field that has voided a series

Please agree the **semantics** in writing, in these words, before the counted
game.

Read strictly ("both verdicts exchanged and clean") the flag is **unreachable**
in the reference dialect, because both sides' `submit_audit` answer `{"ok": true}`
and neither peer can report its verdict of the other — the blindness is
symmetric. Read as "my audit passed and the exchange completed", it is true on a
clean series.

On 2026-08-21 we filed `false` and our opponent filed `true` on the same 6–0 with
the same signature. That is precisely the contradictory pair rule 35 voids for,
in both directions, on a series where nothing actually went wrong. **We now file
it the second way.** Confirm you do too, or tell us your reading and we will match
it — but it must be one reading, written down, before T.

Related: **claim how the *game* ended, not how the exchange ended.** When the
thief outlasts the step limit, both sides claim survival. Claiming "timeout"
there contradicts the survival your own result file records.

Also: `mutual_agreement.sha256` covers only the symmetric outcome, so two
different pairings ending on identical scorelines produce the same hash. If ours
matches another pairing's, that is construction, not copying — the `game_id`
inside the hashed scope is what ties it to this pairing.

---

## SIX WINDOWS, STRICTLY IN SEQUENCE

We open window N only after N−1 settles. **Please run your two roles as one
sequential series, not two concurrent ones.** A peer that dials a window we have
not opened yet gets no greeting and scores itself a phantom technical loss — and
then the two report files disagree about a game that never happened.

Three flags to settle here, all of which default **off** on our side:

1. **Per-sub-game re-handshake.** Does a fresh `negotiate` open every window, or
   does one session hold the whole series? najamjad's contract requires a fresh
   one per window and a peer that holds one session leaves them waiting at every
   handover. Their words: *"One evening was lost to exactly this."* We support
   both; tell us which.
2. **Re-offering a failed window.** najamjad re-offers window N under its own
   number rather than advancing past it, bounded at 2 attempts, and we support
   that. Our default elsewhere is **0** — and a peer that does *not* re-offer
   reads our replay of N as a stale duplicate. Say `0` or `2`.
3. **End-of-series consensus digest.** Some contracts exchange an explicit
   consensus digest after the last sub-game. It rides on `submit_audit`, so a
   peer that does not expect it there sees an audit package with no records —
   which turns a clean series into a technical loss on *their* side. Ours is off
   unless your contract specifies it. Say yes or no.

Keep both roles up until all six settle. Our report fires only on a full 6/6.

**Handshake patience.** Ours defaults to 180 s for the opening handshake and 90 s
for each re-handshake. Against najamjad we raised both to **1000 s** on wall
clock, because their figure was far higher than ours and that made *us* the side
manufacturing the failure — whichever peer runs out first is indistinguishable
from a broken opponent. Please send your numbers and we will raise ours to meet
them.

---

## THE COLD START — measured, and the most common way our pairings die

Three numbers from our own machine, none of which are in anyone's code:

- **Our peer takes about 3 minutes to bind its port** (WSL serving a Windows
  mount; the process sits in `D` state and is not hung). Please do not diagnose
  us dead before three minutes have passed.
- **The connect window is only about 2.5 minutes** before a peer gives up with
  "opponent never came up". Boot time is *longer* than the window it then gets —
  so both sides must start within about a minute of each other, or the slower
  side dies alone.
- **A 502 from a tunnel means "tunnel is up, nothing behind it yet"**, and is
  indistinguishable from a broken tunnel. Our engine is genuinely up only when a
  `GET /mcp` answers 405/406, not 502. Tunnels outlive peers, so a quick-tunnel
  URL stays valid across peer restarts.

The choreography we suggest:

> open tunnels → exchange URLs in writing → both probe until the other's 502
> clears → then both start peers within a minute of each other.

If you would rather hold and let us dial you, name it and we will match. We just
need to agree the direction before T, rather than both waiting politely for the
other.

We are happy to run a 30-second read-only probe (`tools/list`) against your door
hours before T, and to hold ours up for yours. It spends no window.

---

## REPORTS

**Friendly:** mutual exchange, please. Your report to **apexmediamind@gmail.com**
and ours to your operator inbox. A report each side files only to itself cannot
be checked by the other, and reading each other's artifacts is how three
opponents have found real bugs in our implementation. The lecturer is never
involved in a friendly.

**Counted:** to the league address alone (**rmisegal+uoh26finalgame@gmail.com**),
one report per team, sent separately — then we exchange message-ids and forward
each other our copy for byte-reconciliation. We withhold a counted report unless
all six sub-games settled with verified audits; a broken series files nothing
rather than something contested.

**Truthful game-count declaration (rule 37):** ours will say **seven** counted
games played before this one, making yours our eighth. If we ever run two counted
matches at once on two machines we pre-assign the numbers in writing, because
"how many came before" is undefined for simultaneous events.

---

## OUR DETAILS

| | |
|---|---|
| `group_id` / `group_name` | `ahk-yosi` |
| members | 213314859, 325811255 |
| `schema_version` | 1.2 |
| dialect | reference-v3 **and** native, both served on one port |
| topology | ONE process, ONE port, roles alternate internally |
| cop repo | https://github.com/yosefshanaa/p2p-police-agent |
| thief repo | https://github.com/yosefshanaa/p2p-thief-agent |
| workspace | https://github.com/yosefshanaa/final_Project |
| contact | apexmediamind@gmail.com |
| counted games played | 7 (orcai-mj, amireman/G012, saedshki, s82kma9e, gal-roy1, uoh-ay26, najamjad) |
| token budget | 200000 per series |

Our verbal channel can run at **zero tokens** (templated banter) if your deadline
is tight — say the word and we set it. We mention it because our LLM provider has
a 30 s step deadline of its own and could otherwise push a single turn against
your per-turn timeout.

We will send our `game.json` and its `config_sha256` with our first reply so you
can byte-diff before we ever connect — remembering the diff is informative, not a
gate.

---

## WHAT WE NEED BACK FROM YOU

1. `group_id` — exact, lowercase, no spaces
2. MCP endpoint URL(s), and whether one URL serves both your roles
3. Your dialect (reference-v3 / native / other) and your tool names
4. Your 14 terms in the canonical one-line form above, so we diff strings rather
   than eyeball them
5. `schema_version`
6. Scent model, plus the hash **you** compute for it
7. **Which side of the decay** you cut the transmitted packet from (ask 3)
8. **A commit golden vector**: payload, nonce, digest (ask 4)
9. Capture claims: `always_claim`, or threshold?
10. Enclosure: who declares it — cop or thief?
11. `mutual_agreement.confirmed`: your reading, in words
12. Series label: `label <NAME>`, or explicitly `unlabelled`
13. Which role your peer opens window 1 with, and whether roles alternate
14. Window re-offers: 0 or 2
15. Per-sub-game re-handshake: yes or no
16. End-of-series consensus digest: yes or no
17. Your handshake / re-handshake patience, in seconds
18. Your topology: one process or two — we will not make it a settlement issue,
    each side simply declares its own
19. Your operator inbox, for the friendly report exchange
20. Repos + per-role commit SHA. If your repos are private, say so up front — the
    declaration carries URL + SHA and nothing in the audit needs source access.

---

## PROPOSED SEQUENCE

1. You send the twenty above. We exchange pre-derived pairing values (`game_id`,
   `game_uid`, our `game.json` + sha) and diff the 14 terms as strings.
2. A 30-second read-only probe in each direction, hours before T. It spends no
   window and catches surface mismatches early.
3. **Friendly #1** — full six sub-games, nothing filed or emailed to anyone but
   each other. Then both sides byte-reconcile every artifact in both directions:
   config, log, result, declaration, `mutual_agreement.sha256` and `confirmed`.
4. Fix whatever surfaces, then lock a counted T with written authorization
   (declaration + quote-back with the exact time).

Looking forward to a clean series.

— **ahk-yosi** (Ahmad & Yosef)
apexmediamind@gmail.com
