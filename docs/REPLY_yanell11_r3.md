=== ahk-yosi -> yanell11, round 3 ===

Nell, Yanal — thank you for the turn-order fix, and for the verbatim §2.4.2. Both of
those cost you something to send and both were the right call.

Status: **settlement is fully agreed and verified.** Terms, commit digest and result
digest all reproduce on our side. The scent lock is the only thing left, and we think
we can close it with no code change on either side — details in §3, including numbers
you can diff against your own emitter in about a minute.

---

## VERIFIED ON OUR SIDE (three for three)

**1. Your result-digest golden vector reproduces through our own code.** Not a
re-implementation of your rule — our shipped `mutual_signature()`, fed your scope:

```
ours:   f0f83af87f15ca5bd3584c3ffca167a94e0e4e7c91665d3b4f3e451746e93a75
yours:  f0f83af87f15ca5bd3584c3ffca167a94e0e4e7c91665d3b4f3e451746e93a75   MATCH
```

Your bytes also round-trip exactly through `json.dumps(sort_keys=True)`, so the spaced
settlement form is confirmed on the wire and not just in prose. For the record, the
compact encoding of that same document gives `328c6ec6…` — the wrong-but-plausible hex
string we both have to avoid. Our signed scope is identical to yours: `game_id`,
five aggregate keys (`total_score`, `sub_games_won`, `ties`, `winner_group`,
`series_tie`), five per-row keys (`sub_game_number`, `roles`, `result`,
`winner_group`, `score`), scores keyed by **group id**, role spelled **`police`**.

**2. Your 14 terms are byte-identical to ours.** We diffed them as strings. With
`setting` set to Haifa there is exactly **zero** difference — not one key. On our side
`setting` is a negotiable environment override, so adopting Haifa costs us no code and
no committed edit.

**3. Your three extras collide with nothing.** We grepped our whole source, config and
lock tree for `interop_profile`, `tie_award` and `turn_order`: **no hits.** We emit none
of the three, so you will see silence on all three, which by your rule is fine. No
action needed either way.

---

## A) TURN ORDER — your fix is right, and we still owe you one more caveat

Your diagnosis is exactly the split we should have made ourselves: opening ROLE and
within-turn MOVE ORDER are two different things and we ran them together. Declaring
`turn_order="thief_first"` to match what your loop already played is the right fix.

The caveat, because it has not gone away: **our guard still cannot verify this.** As we
told you last round, our reference adapter synthesises `first_mover: "thief"` on your
behalf when it builds your handshake record — it states a fact about the reference
implementation rather than reading your wire. So your declaration is invisible to our
checker. What changed is not our verification; it is that your wire play, your
declaration and our hardcoded assumption now all say the same thing, which is what we
actually needed. We are relying on your word and your commit, and we would rather say so
twice than let it read as a guarantee.

Settled: thief moves first within each turn; you open windows 1/3/5 as thief, we hold
police on 1/3/5. No collision.

---

## 3) THE SCENT LOCK — four options, honestly priced

You asked straight, so here is our side without spin, including what each option costs
**us**.

First, one correction to the framing. You wrote that `934c220d` "is exactly the kit's
registered book document you named." That is right — and it is not a document we hold.
Our three models hash to:

```
book_v1                    ea7225f5d71989add99a0057287342b7c5b86ab4efffd1608da25d0e368c0a28
registered_v3              0761ca169ee93a11cb19e6e28251074ab7223bdb157ec5123138d87aad651f6f
subtractive_chebyshev_v1   81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4
```

**(a) We declare/serve `934c220d`.** We cannot do this today — we do not have those
bytes, and we will not declare a hash we cannot recompute, for the same reason you
declined to echo `81ebee59`. If you send the exact JSON bytes we will verify the digest
and price registering it as a fourth model. It is a real code change on our side and it
would be a physics we have never tuned a doctrine for, so it is our slowest option.

**(b) We make the lock advisory.** No such switch exists in our peer — we looked. There
is no config flag, no environment override; `check_compatibility` refuses on a
scent-hash difference unconditionally. Making it advisory is a code change to a safety
property, and we would rather not: it is the only thing standing between two peers and
six windows of silently different physics, and this pairing is headed for a counted
game. Declining this one, and saying why rather than just saying no.

**(c) You add `subtractive_chebyshev_v1`.** Zero code for us — which model we declare is
already an environment variable. You have decoded najamjad's subtractive field at zero
cost, so the reading half is proven on your side; the work is the emitting half. This is
our **preferred** option on the merits, and we will not pretend otherwise: our archive
says the multiplicative clamped family blunts both halves of a match relative to
subtractive, because a clamped field ties a whole region at the ceiling and neither side
gets a clean positional fix. That is a reason we want it, not a reason you should agree.

**(d) You adopt our `registered_v3` document.** Zero code for **both** sides, and we
think this is the one that actually closes today.

### Why (d) is not "declaring a model you don't emit"

Your objection to echoing `81ebee59` was principled and we respect it. It does not apply
here — by your own item 4 you already emit this physics. Read your description back
against our document: multiplicative decay, rho 0.1, clamped `[0, 0.9]`, packet served
at peak deposit, freshest centre 0.9. That is `registered_v3` line for line. The only
thing that differs is the internal version label — ours reads `multiplicative_book_v3`,
yours reads `multiplicative_book_v1` — which is the entire reason the digests differ.

The document is one line, and it is the whole thing:

```json
{"center_intensity":0.9,"dust_floor":null,"evaluation_order":"(1 - rho) * tau + delta","formula":"tau(t+1) = clamp((1 - rho) * tau(t) + delta_tau, 0, 0.9)","kernel":[[0.04,0.14,0.2,0.14,0.04],[0.14,0.42,0.62,0.42,0.14],[0.2,0.62,0.9,0.62,0.2],[0.14,0.42,0.62,0.42,0.14],[0.04,0.14,0.2,0.14,0.04]],"model":"multiplicative_book_v3","numeric_example":{"delta":0.04,"result":0.085,"tau":0.05},"rho":0.1,"rounding_digits":null,"serving":"each step serves the field AFTER that step's own update"}
```

It lives in our repo at `docs/locks/scent_registered_v3.json`, written as canonical bytes
with no trailing newline, so the file's own digest IS the wire value — you can check it
with `sha256sum` alone, without running any of our code:

```
sha256sum docs/locks/scent_registered_v3.json
0761ca169ee93a11cb19e6e28251074ab7223bdb157ec5123138d87aad651f6f
```

### Don't take our word — diff the served numbers

This is the check that actually settles it. Here is the field our `registered_v3` serves
on the **first** step, thief standing at (3,3), on an empty grid:

```
   0.0400  0.1400  0.2000  0.1400  0.0400
   0.1400  0.4200  0.6200  0.4200  0.1400
   0.2000  0.6200  0.9000  0.6200  0.2000
   0.1400  0.4200  0.6200  0.4200  0.1400
   0.0400  0.1400  0.2000  0.1400  0.0400

centre 0.9000   orthogonal 0.6200   diagonal 0.4200   ring-2 0.2000
```

Step 2, thief moves to (3,4): new centre `0.9000`, the just-vacated cell also `0.9000`
(both pinned at the clamp — that is the clamped-field behaviour we described).

Run your emitter on the same two steps. If those numbers come out of your kernel, our
document describes your physics and you can adopt it honestly. **If your 5×5 kernel is
not the one above, then `registered_v3` is not your document either** and we are back to
(a) or (c) — so please diff before agreeing, rather than after.

And the trap once more, since it has bitten twice already: do **not** reach for our
`book_v1` because the name is closest to yours. It serves **pre-emission** — an all-zero
field on step 1, then 0.558 at the new centre and 0.810 at the vacated cell. Closest
name, furthest physics.

**Our ask: (d) if your kernel matches, (c) if you would rather do the work and get the
better physics. Either is zero code for us and we can move immediately on your word.**

---

## 6) THE FIVE SETTINGS — where we land

- **Capture claims.** Understood and accepted as your call; we are not asking you to
  self-handicap and we agree it voids nothing. We will run **threshold** on our cop. No
  further discussion needed — we just did not want you surprised by the asymmetry.
- **Enclosure.** Agreed: thief concedes, one reporter, thief side. We will run our
  cop-claims-enclosure **OFF**. Flagging that our default is ON, so this is an explicit
  per-opponent setting on our side, not a no-op.
- **Label / uid.** We will take your `game_id` **verbatim**:
  `ahk-yosi-vs-yanell11-friendly-1`. That one genuinely matters — it is the first signed
  key of the result digest, so a difference there breaks a clean 6/6 at the last step.
  On the `game_uid` we have news that makes this a non-issue: we went and checked, and
  **`game_uid` is never compared anywhere in our peer** — not in the compatibility gate,
  not in the result digest, not in the consensus digest. It reaches artifacts and logs
  and nothing else. So the two rules can differ harmlessly. For the record, on the agreed
  Haifa terms:
  ```
  ours  (pair-seeded)   9bb658ea-115b-ba62-e722-231e85ab340b
  yours (label-seeded)  a0b99406-11d1-384c-823c-0315c9596bab
  ```
  Both computed, both correct under their own rule. Expect ours in our filenames; we will
  expect yours in yours. If you would rather we match, say so and we will price it — but
  we do not think it buys anything.
- **Per-sub-game re-handshake.** YES, agreed. We will enable it.
- **Window re-offers.** 0, agreed — already our default.

---

## 7) OUR TWO GOLDEN VECTORS

**Commit** (reference form, nonce OUTSIDE, compact canonical JSON):

```
payload (canonical):
{"barrier":null,"hint":"","intent":"hold","kind":"step","move":"STAY","pos_after":[0,0],"pos_before":[0,0],"position":[0,0],"role":"police","scent":[],"state":[0,0],"step":0,"sub_game":1,"sub_game_number":1}

nonce:   ffeeddccbbaa99887766554433221100
digest:  cdcaaab1273ef50a9c67ac41881720f644ca06147eebc5c901e559096f8c8cbd
formula: sha256(canonical_json(payload) + "|" + nonce)
```

Same formula as yours, on a real sealed record rather than an illustrative one so you
also see our actual field set. `sub_game` and `sub_game_number` are both sealed
deliberately: it lets a peer bucket our reveal by content rather than by arrival time.
Bucketing by arrival is unsound once two peers cross a window boundary at different
instants — an opponent who did it filed our window-N reveal against their window N+1,
zero commitments bound and every role label inverted.

**Result digest** (spaced settlement form). Illustrative 5-1 / 85-45 — reproduce the
digest, not the scoreline:

```
scope:
{"aggregate": {"series_tie": false, "sub_games_won": {"ahk-yosi": 5, "yanell11": 1}, "ties": 0, "total_score": {"ahk-yosi": 85, "yanell11": 45}, "winner_group": "ahk-yosi"}, "game_id": "ahk-yosi-vs-yanell11-friendly-1", "sub_games": [{"result": "capture", "roles": {"ahk-yosi": "police", "yanell11": "thief"}, "score": {"ahk-yosi": 20, "yanell11": 5}, "sub_game_number": 1, "winner_group": "ahk-yosi"}, {"result": "survival", "roles": {"ahk-yosi": "thief", "yanell11": "police"}, "score": {"ahk-yosi": 10, "yanell11": 5}, "sub_game_number": 2, "winner_group": "ahk-yosi"}, {"result": "capture", "roles": {"ahk-yosi": "police", "yanell11": "thief"}, "score": {"ahk-yosi": 20, "yanell11": 5}, "sub_game_number": 3, "winner_group": "ahk-yosi"}, {"result": "capture", "roles": {"ahk-yosi": "thief", "yanell11": "police"}, "score": {"ahk-yosi": 5, "yanell11": 20}, "sub_game_number": 4, "winner_group": "yanell11"}, {"result": "capture", "roles": {"ahk-yosi": "police", "yanell11": "thief"}, "score": {"ahk-yosi": 20, "yanell11": 5}, "sub_game_number": 5, "winner_group": "ahk-yosi"}, {"result": "survival", "roles": {"ahk-yosi": "thief", "yanell11": "police"}, "score": {"ahk-yosi": 10, "yanell11": 5}, "sub_game_number": 6, "winner_group": "ahk-yosi"}]}

mutual_signature = 4bd1d3eb07c229f3da8f4926f24928a4247dd65452dfc16e7b1e616c0f8df29c
```

Note it exercises a **survival** row and a **series winner**, which your all-capture tie
sample does not — between the two vectors we now cover both result words and both
`series_tie` branches.

---

## 8) §2.4.2 AND APPENDIX ה — thank you, and we are taking it seriously

You did not have to send the verbatim text, and sending it with your own overstatement
corrected in the same breath is the most useful thing in your message. You have read our
topology correctly: we hold one role at a time and never run cop and thief concurrently,
so #2 (no shared live state) is not where our exposure is — #1's letter, two separate
processes, is. That is a real gap in our submission and it is ours to close. We are not
going to resolve it in a reply to you, but we would not have looked at it this week
without your paragraph, so: thank you.

Agreed it is not a settlement issue for the friendly, and on match day we are on separate
machines from you regardless.

---

## THE REST — acknowledged, no action

- **`confirmed`**: same reading. Good.
- **Field names**: agreed, the digest is what must match, and it now does — twice.
- **Consensus**: our envelope shape matches yours field for field; ours is on and linger
  is set to 600s.
- **Counted**: agreed on all four. `counted_games_played` on our wire will be **7** —
  re-derived just now from our filed match artifacts (game numbers 1 through 7, no gaps),
  not quoted from a note. One caveat we owe you: our team may run a second counted series
  concurrently with a different opponent, and the counter has no shared state, so if that
  happens the number you read is still ours and still correct — it is assigned per launch,
  not per wall clock.
- **Emails**: ours to yanalserhan3@gmail.com, yours to apexmediamind@gmail.com. Confirmed.
- **Cold start**: 1000s opening wait both sides, ~180s per turn, 405/406 means up, 502
  means the tunnel is there and the peer is not. A 30s read-only `tools/list` probe each
  way beforehand — yes please, and we will do the same to you.
- **Doors**: one URL from us serving both our halves; we will dial your cop door on
  windows 1/3/5 and your thief door on 2/4/6.

---

## WHAT WE NEED BACK

1. **The scent path**: (d) if your kernel matches the 5×5 above — please diff the served
   numbers first — or (c) if you would rather implement subtractive. If neither, send us
   your `934c220d` bytes and we will price (a).
2. Your two tunnel URLs, fresh, held up for the run.
3. Your new commit SHA after the turn-order fix.
4. A proposed time.

Everything else on our side is settled and configured. Once the scent path is chosen we
can start within the hour on our end.

— ahk-yosi (Ahmad Kaiss, Yosef Shanaa)
apexmediamind@gmail.com
