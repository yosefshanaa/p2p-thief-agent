# P2P Cop–Thief — Interoperability Guide

**Team `ahk-yosi`** · Yosef Shanaa (213314859), Ahmad Kaiss (325811255)
Cop repo: <https://github.com/yosefshanaa/p2p-police-agent> · Thief repo: <https://github.com/yosefshanaa/p2p-thief-agent>

This is everything you need to play us without reading our code. Every formula below is
published as a **literal derivation with a golden vector**, so you can reproduce it before
the first move instead of agreeing to it and finding out later. If any value you compute
differs from ours, tell us — that is the whole point of this document.

We have played four opponents. Every single defect that cost a real sub-game was invisible
in a short healthy-looking warm-up and surfaced at a sub-game boundary or in the final
audit. §12 lists them, because they will cost you too.

---

## 0. The five-minute version

| | |
|---|---|
| **Transport** | MCP over HTTP at `/mcp`, no auth, `stateless_http` |
| **Dialects** | We speak **both** — see §2. Tell us which you run; nothing changes on your side |
| **Commit** | `sha256(canonical_json(payload) + "\|" + nonce)` — §3 |
| **Board** | 7×7, cop `(0,0)`, thief `(3,3)`, top-left origin, index 0 |
| **Length** | 35 steps, 14 barriers, 6 sub-games, thief moves first |
| **Scoring** | capture 20/5, survival 5/10, tie 2, technical loss 0 |
| **Turn timeout** | 180 s. Silence past it forfeits that sub-game |
| **Audit** | Per sub-game, after it ends. **The envelope names its sub-game** — §7 |

**What we need back:** your `/mcp` URL, your repo URL, your dialect, your commit golden
vector, your scent physics as an expression, whether roles alternate, whether you
re-handshake per sub-game, who announces enclosure, your prior counted-game count, and a
wall-clock start time. Template in §13.

**If you build against [`copthief-league-protocol`](https://github.com/Imreec/copthief-league-protocol)**
(teams imreeyal and anrbj666), most of that is already settled between us: our implementation
reproduces every CORE vector in that kit — canonical JSON including non-ASCII and float
round-trip, the commit seal, both deterministic ids, the terms signature, and the settlement
digest in its spaced encoding. Those vectors are vendored into our own suite as
`tests/unit/test_kit_conformance.py`, so the claim is checked on every commit rather than
asserted here. **Two things the kit leaves open still need agreeing per pair: which scent
model (§6) and who announces enclosure (§9).**

---

## 1. Order of play

1. **Exchange contracts** (this document, and yours).
2. **Reproduce each other's golden vectors** — §3, §5, §6. Costs minutes, saves a series.
3. **A full six-sub-game friendly**, uncounted, nothing filed or emailed.
4. **The counted match.**

We insist on a **full six** rather than one or two, because role alternation, per-sub-game
re-handshakes and the audit bucketing only fail from sub-game 2 onward. A two-game warm-up
passes and then the counted match dies at the boundary. We have watched it happen.

The book allows exactly **one counted encounter per pair**, sealed the moment both reports
are filed. Anything that can break should break in the friendly.

---

## 2. Wire dialects

We implement both and adapt to you. Tell us which you run and we set one flag.

**Native (ours)** — request/response, four phases:

```
handshake(payload)        -> our handshake payload
receive_commit(msg)       -> {"ack": true, "locked": true}
receive_reveal(pub)       -> {"ok": true, "events": [...]}
receive_event(envelope)   -> {"ok": true}
audit_exchange(package)   -> {"verdict": "...", "violations": [...]}
health_check()            -> {"ok": true, ...}
get_status()              -> local-truth snapshot (monitoring only, never ground truth)
```

**Reference family** — push-and-inbox, every tool returns `{"ok": true}` and the reply
arrives later as a separate call into *your* server:

```
negotiate(message)        receive_turn(message)
submit_audit(payload)     receive_control(message)
```

Our server answers **all of the above simultaneously**, so you do not need to know which
we prefer. We probe your endpoint and classify it before playing:

```bash
uv run p2p-pursuit smoke https://your-url/mcp     # prints dialect=native|reference|unknown
```

If the probe disagrees with your prose, we trust the probe and ask.

---

## 3. The commitment — reproduce this first

Canonical JSON, used for **every** hashed payload in our system:

```python
json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

Sorted keys, compact separators, UTF-8, **no spaces**, non-ASCII preserved.

The commitment over a nonce-free payload:

```
commit = sha256( canonical_json(payload) + b"|" + nonce.encode("utf-8") ).hexdigest()
```

### Golden vector — trivial

```
payload = {"a": 1}
nonce   = "abababababababababababababababab"     (32 hex chars = 16 bytes)
commit  = 2d5faf71c42626d681a5727c2e7940af4c8e21e7f59f3acd6e063ae654bcee0a
```

### Golden vector — a real step record

> **Changed 2026-08-18.** The record now also carries `state` and `position` — the
> reference family's names for where the mover ended up, duplicating our own
> `pos_after`. A validator that reconstructs the trajectory reads `state`, and ours
> carried neither, so uoh-ay26's audit saw `state: null` on every step and could not
> verify continuity. If you hold an older copy of this vector, use the one below.

```
payload (canonical form, exactly these bytes):
{"barrier":null,"hint":"north side","intent":"lie","kind":"step","move":"E","pos_after":[3,4],"pos_before":[3,3],"position":[3,4],"role":"thief","scent":[[0.0,0.0],[0.0,0.81]],"state":[3,4],"step":1,"sub_game":1,"sub_game_number":1}

nonce  = abababababababababababababababab
commit = 9213349e8d9ae511506f224cb2d8662c095e17d506b06cf594e092b6c5bbbf60
```

**If you reproduce both, our audits will bind. If you do not, neither side can verify the
other and we should find out now.** Send us yours and we will reproduce it before we play.

> We also have a second, internal digest that hashes the record *with* the nonce inside it.
> It is selectable per match and we default to the formula above for every cross-team game.
> Ignore it unless you ask us for it.

---

## 4. The constitution

Our committed `game.json` currently hashes to:

```
a7933121447441e1c7bca2962ce92e26374f1b5eb62355d441b9b0aa7a40e7f8
```

**That number is per-pairing, not per-repo, and yours will differ from ours.** `agreed_between`
names both teams and sits inside the hashed object, so the digest changes the moment we name
you — as it must. Do not treat a difference here as a mismatch to reconcile; ask instead
whether the *terms* agree.

**What actually gates the game depends on which family you are.** If you speak our native
dialect, the whole-file hash is compared by exact equality and any mismatch refuses. If you
speak the **reference family**, it never crosses the wire at all: your greeting carries no
constitution hash, so the constitution *is* the 14 flat signed terms below, and
`interop_codec.handshake_from_agreement` mirrors our own lock hashes into the comparison
**only** when your terms match ours exactly and your signature verifies. A reference peer
therefore has one thing to diff, not two — the 14 terms — and those are invariant across
pairings.

Send your `game.json` back if you want any value changed and we will adopt it — minimums may
only rise. We keep per-opponent config directories, so adopting your values never leaks into
another team's match.

The book defaults it encodes:

| | |
|---|---|
| board | 7×7, top-left origin, index 0 |
| starts | cop `(0,0)`, thief `(3,3)` |
| length | 35 steps, 14 barriers, 6 sub-games |
| first mover | thief |
| scent | τ₀ = 0.9, ρ = 0.10, 5×5 kernel |
| scoring | capture cop 20 / thief 5 · survival cop 5 / thief 10 · tie 2 · technical loss 0 |
| hints | max 15 words |

### The 14 signed terms

If you belong to the reference family, this is our constitution in your vocabulary. Values
**and JSON types** must match exactly — your `verify_peer` compares by dict equality.

```json
{
  "axis_origin_corner": "top-left",
  "axis_start_index": 0,
  "barriers_max": 14,
  "board_size": 7,
  "cop_start": [0, 0],
  "decay_per_step": 0.1,
  "emit_intensity": 0.9,
  "hint_max_words": 15,
  "max_steps": 35,
  "min_center_intensity": 0.5,
  "num_games": 6,
  "setting": "New York",
  "smell_grid_size": 5,
  "thief_start": [3, 3]
}
```

`setting` is the value most likely to differ — one opponent used `"Haifa"`. It is a label,
we do not care which, and we will adopt yours. **Say so explicitly**, because it is inside
the signature and a one-word difference refuses every handshake.

---

## 5. Deterministic identifiers

Both sides derive these independently and must land on the same values. That is the point:
a mismatch surfaces at the handshake instead of quietly labelling this series with a stale id.

```python
game_id  = "-vs-".join(sorted([group_a, group_b]))

material = canonical_json(terms) + b"|" + lo.encode() + b"|" + hi.encode()   # lo, hi = sorted slugs
game_uid = str(uuid.UUID(bytes=sha256(material).digest()[:16]))             # first 16 RAW bytes
```

### Golden vector (against the 14 terms above)

```
ahk-yosi + amireman  -> game_id  ahk-yosi-vs-amireman
                        game_uid 4cada35c-bba4-72c7-0838-d6fd723e13b8
ahk-yosi + uoh-sqak  -> game_id  ahk-yosi-vs-uoh-sqak
                        game_uid 52d2d904-28d5-50f0-54d3-5842ad94f198
```

**Confirm you derive the same `game_uid` before the first move.** If it differs, our terms
differ in a byte, and the handshake is the cheap place to learn that.

**An agreed label** (e.g. `G012`) may replace the derived `game_id`. It is a top-level key
of the consensus object (§8), so a label set on one side only is a **guaranteed digest
mismatch on an otherwise clean series**. Agree it in writing, and never override the `uid`.

---

## 6. Scent physics

Publishing the kernel is not enough — the **serve order** matters and most guides omit it.

```
tau(t+1) = min(0.9, max(0, (1 - rho) * tau(t) + delta_tau))
rho = 0.1        center_intensity = 0.9        rounding = 4 digits
serving: each step serves the field BEFORE that step's own emission
```

5×5 emission kernel, radial by `(|dr|, |dc|)`:

```
0.04  0.14  0.20  0.14  0.04
0.14  0.42  0.62  0.42  0.14
0.20  0.62  0.90  0.62  0.20
0.14  0.42  0.62  0.42  0.14
0.04  0.14  0.20  0.14  0.04
```

**One worked number settles the serve order: τ₀ = 0.9 → our freshest cell reads `0.81`, not
`0.9`.** If yours reads 0.9 you serve post-emission. Say which; we run either, and we keep a
registered alternative model we switch to per opponent. What must not happen is the two
sides silently disagreeing.

**If you build against the league kit, you are probably on the other physics.** We implement
all three registrations and select per opponent:

| model | emission | decay | serve order | freshest cell |
|---|---|---|---|---|
| `book_v1` *(book default)* | figure-4 kernel | `τ × 0.9` | pre-emission | 0.81 |
| `registered_v3` (*aka* `multiplicative_book_v3`) | same kernel, no rounding | `τ × 0.9` | post-emission | 0.90 |
| `subtractive_chebyshev_v1` *(kit CORE)* | flat rings 0.9 / 0.6 / 0.3 | `v − 0.1` | `deposit_then_decay` | **0.80** |

The subtractive row's serve order is **not pinned by any kit vector** — it is a per-pair
agreement, and it moves every reading by one step. Ours follows `s82kma9e`'s locked document
(`"order": "deposit_then_decay"`), so our freshest served cell reads **0.80**, not 0.90. If
yours reads 0.90 you decay before you deposit; say so and we will match you.

These are not spellings of one model. Under subtractive decay a 0.3 cell is gone in three
steps; under multiplicative it is still 0.2187 — a completely different trail memory, which
is why we keep a separately searched doctrine per physics and select the pair together.

**We are happy to play any of the three, including yours.** If you build against the kit and
run `subtractive_chebyshev_v1`, just say so and we will bring the doctrine searched under it —
no negotiation needed. Whichever we agree, both sides exchange the hash of the model document
before the first move, so the choice is on the record rather than in a mail thread. Ours are:

```
book_v1                    ea7225f5d71989add99a0057287342b7c5b86ab4efffd1608da25d0e368c0a28
registered_v3              0761ca169ee93a11cb19e6e28251074ab7223bdb157ec5123138d87aad651f6f
subtractive_chebyshev_v1   81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4
```

The subtractive hash is `s82kma9e`'s canonical document adopted **byte-for-byte**, because a
document that merely describes the same physics in different words hashes differently and a
kit handshake refuses on a scent-hash mismatch. If yours differs, send us the JSON and we will
adopt yours rather than argue about vocabulary.

On the wire the field is sparse — `{"r,c": intensity}`, zeros dropped:

```json
{"3,3": 0.9, "3,4": 0.62, "2,3": 0.62}
```

---

## 7. The audit — read this section twice

After each sub-game, both peers reveal every `(payload, nonce)` that produced a commitment
sent during it. This is the part that has broken in **every** cross-team series we have
played, including ours.

### The envelope

```json
{
  "sender": "police",
  "sub_game": 5,
  "sub_game_number": 5,
  "records": [ {"payload": {...}, "nonce": "...", "commit": "..."} ],
  "result_claim": "capture"
}
```

**The envelope names its sub-game, in both spellings, and every record repeats the index
inside its own payload as `sub_game` and `sub_game_number`.** Please bucket on one of them.

### Why this matters more than it looks

Do **not** file an incoming audit by *when it arrives*. The two peers do not cross a
sub-game boundary at the same instant: a peer that waits for the opponent's package before
advancing always receives on time and always sends late. Its sub-game *n* reveal lands in
your sub-game *n+1* bucket, and then:

- none of the commitments bind — you will see `0 of N`;
- with role alternation, **every role label reads inverted**, because a package read one
  index late is always the opposite role;
- the record count is the *previous* sub-game's, which looks like a truncated reveal.

That was a real 0-of-N failure across a whole six-game series, and the diagnosis cost a day.
It was never a hashing problem. **Bucket by declared index, then by record content, and only
then by arrival.**

### What we check in your reveal

1. every revealed record re-hashes to its own commitment;
2. **every commitment you sent in play is revealed** — your own audit may not check this,
   and without it a peer can withhold an inconvenient step;
3. your trajectory is physically continuous on the agreed board.

For a match played in one dialect on both sides we additionally re-derive scent honesty,
barrier quota and capture-claim truthfulness from your records.

### What we promise about ours

- The `commit` we reveal is the commitment **we actually sent live**, never re-derived at
  audit time. Re-deriving makes a broken package pass its own verification while binding to
  nothing you hold — we shipped that bug and it is exactly how it hides.
- Nothing is generated during the audit. Payloads and nonces are sealed when the step is
  played and frozen the instant the sub-game ends.
- Only records belonging to that exact sub-game, with the role that actually played it.
- We run your check against our own package **before sending it**, and file the result into
  our own log artifact.

You can re-run the whole thing offline against our sealed artifacts:

```bash
uv run p2p-pursuit verify --dir <match dir>
```

---

## 8. End-of-series consensus (optional, recommended)

If your contract specifies one, we speak this exchange. Three keys, rows ascending, **compact
separators**, group-keyed so sorted-key JSON is byte-identical on both sides:

```json
{"game_id": "...", "game_uid": "...", "sub_games": [
  {"sub_game_number": 1, "result": "survival",
   "roles": {"team-a": "police", "team-b": "thief"},
   "score": {"team-a": 5, "team-b": 10}, "winner_group": "team-b"}
]}
```

`result` ∈ `capture | survival | timeout | technical_loss | tamper_forfeit`. **`technical_loss`
must survive verbatim** — aliasing it to `timeout` still produces 64 valid hex characters and
a silently wrong digest.

`consensus_sha = sha256(canonical_json(document)).hexdigest()`

### Golden vector

```
{"game_id":"a-vs-b","game_uid":"uid-1234","sub_games":[{"result":"survival","roles":{"ahk-yosi":"police","them":"thief"},"score":{"ahk-yosi":5,"them":10},"sub_game_number":1,"winner_group":"them"},{"result":"capture","roles":{"ahk-yosi":"thief","them":"police"},"score":{"ahk-yosi":5,"them":20},"sub_game_number":2,"winner_group":"them"}]}

sha = 3d2eddb4692b0a42fa3b01a37ad9241f40734687730be4f74724c5b115443764
```

Exchanged in a `submit_audit` envelope carrying `result_claim: "series_consensus"` and
`records: []`. **Intercept that envelope before your audit handler sees it** — it has no
records, so auditing it as a log writes an empty-log verdict over the last sub-game's real
one and turns a finished series into a technical loss.

**`confirmed` is a per-side gate.** Ours being true says nothing about yours. Please send us
your `consensus_sha` and your `confirmed` at the end; we will send ours. We have had a series
where both sides read `match: true` from their own chair and only one was actually confirming.

---

## 9. Series conventions — neither is settled by the book

Both are pair-negotiated and both default to **off** on our side. Getting either wrong voids
a match from sub-game 2 onward while sub-game 1 looks perfect.

- **Role alternation.** Natural role on sub-games 1/3/5, opposite on 2/4/6. Say yes or no.
- **Re-handshake per sub-game**, or one handshake per series. Say which.
- **Enclosure** (a thief with no legal move, book §3.4): does your **thief announce** it,
  does your **cop claim** it, or is the rule off? **Exactly one side may report it**, or the
  series desynchronises. Three opponents in a row wanted thief-announced, which is also what
  the league kit settles on (SPEC §3.1) and what we default to.

  Under that convention our thief announces both endings only it can see — a barrier dropped
  on its own cell (rule 46) and no legal move left (rule 47) — as
  `claim_response: {"claim": [<our own cell>], "caught": true}`, the same shape as a
  co-location answer, because `win_claim` is reserved for survival. Our cop settles capture
  on **any** `caught: true` you send, whichever cell it names.

  We also **corroborate** a conceded cell against our own barrier record and write the verdict
  into the log and result (`concession corroborated` / `NOT corroborated`). To be explicit
  about what that is and is not: it is evidence, not a sanction. We do not withhold your
  points over it, because a false concession pays *both* sides and neither of us should be
  the one grading it — the artifacts are.
- **Capture claim.** If your contract makes the cop's claim protocol-level and unsuppressable
  every turn, say so — we gate ours behind a belief threshold by default, and under your rules
  that silently forfeits captures we earned.

---

## 10. Timing and cold start

- **180 s per turn.** Silence past it forfeits that sub-game as a technical loss.
- Our peer takes **~3 minutes to boot**. If your peer waits only ~60 s for our agreement
  before exiting, starting first will burn your window.
- **Propose a wall-clock minute** and have both peers up before it.
- **If indices ever disagree mid-series, the peer that is behind joins the one ahead** rather
  than restarting. Two peers that both advance on failure and both insist on their own index
  livelock indefinitely — we have measured it against a live opponent, twice in a row.
- We run matches over a **Cloudflare quick tunnel**. We measured ngrok's free tier dropping
  the MCP session mid-sub-game with both peers healthy, where Cloudflare finished with
  `Verified OK` on both sides. Quick-tunnel URLs rotate on restart, so we re-share ours
  immediately before the match and after any restart.
- Before we launch, `HTTP 502` from a tunnel means **the peer is not up behind it yet** — the
  tunnel itself is fine. A live FastMCP endpoint answers a bare `GET` with `405` or `406`.

---

## 11. Artifacts and reporting

Four artifacts per match, per the book's Appendix F:

```
declaration_<game_id>.json          config_<game_id>_g01.json … g06
log_<game_id>_g01.json … g06        result_<game_id>.json
```

Each sub-game log carries both sides' sealed records **and** the commitments received live,
so any entry can be re-verified independently, by either team, months later. Our declaration
carries a real `started_at` **and** `ended_at`, and each sub-game log carries its own
`started_at`/`ended_at` plus your per-turn wire timestamps, so a filed match can say exactly
when it started and ended without reference to file mtimes.

Both teams email their own report to `rmisegal+uoh26finalgame@gmail.com`; a missing report
forfeits that side's points. **Rule #37:** each side declares its own prior counted-game
count truthfully, and both declarations reach the lecturer.

---

## 12. The five defects that have actually cost us sub-games

Offered because they are cheap to check and expensive to discover.

1. **Audit filed by arrival time** (§7). Caused a 0-of-N audit failure across a whole series
   in both directions. The tell is inverted role labels plus a record count matching the
   *previous* sub-game.
2. **Re-deriving the commitment at audit time.** The package passes its own verification and
   binds to nothing the opponent holds. Reveal the hash you actually sent.
3. **A consensus envelope on the same tool as the per-sub-game audits.** Ours audited it as a
   log, found no records, and filed a technical loss over a completed sub-game.
4. **A short warm-up proving nothing.** Alternation, per-sub-game handshakes and audit
   bucketing all fail from sub-game 2 onward. Play a full six.
5. **A gated capture-claim under a contract that forbids gating.** A turn spent standing on
   the thief without claiming is a capture earned and not scored.

---

## 13. What to send us

```
Team name / group id:
Members (names + ids):
Cop repo URL:                        Cop runtime SHA (40-hex):
Thief repo URL:                      Thief runtime SHA (40-hex):
Public MCP endpoint (/mcp):
One endpoint or two (cop/thief)?

Dialect:                             native / reference / other
Roles alternate?                     yes / no
Re-handshake per sub-game?           yes / no
Enclosure announced by:              your thief / our cop / nobody
Capture claim:                       gated by strategy / unsuppressable every turn

Commit golden vector:                payload + nonce + digest
Scent physics:                       rho, centre, rounding, dust floor, serve order,
                                     and one worked number (ours: 0.9 -> 0.81)
Consensus digest (if any):           object shape + separators + golden vector
game_uid you derive for our pair:    (should match §5)
Constitution:                        yours attached, or "we accept yours"

Prior counted games (rule #37):
Friendly time (wall clock):          Counted match time:
```

The **runtime SHA** is the commit your peer will advertise on the wire, which is not
necessarily your published repo HEAD — we run one peer that plays both roles across a
series, so one runtime SHA covers all six sub-games while our two submission repos sit at
their own HEADs. If yours differ, say which is which.

---

## 14. Our position, plainly

We would rather lose a match to a better strategy than win one because the other side's
audit could not read ours. Everything here is checkable, and if you find a place where our
implementation disagrees with this document, that is a bug on our side and we want to know.

Send us your contract and a time.
