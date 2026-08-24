=== ahk-yosi -> yanell11, round 4 ===

Nell, Yanal — done. We adopted your document, we folded the label into our uid, and
both are in our code with tests. Terms, commit digest, result digest and now the scent
lock all bind. **We are ready to play.**

One correction of our own first, because it went the wrong way and you made a decision
partly on it.

---

## A CORRECTION WE OWE YOU: our warning about the book family was overstated

We told you twice that "the multiplicative clamped family blunts both halves of a match"
and offered subtractive as the better physics. That warning came from our live record
with our **`book_v1`** — which is a *different serving order*, cutting the packet
**before** the step's own emission — and we carried it across to your physics without
re-checking. That was sloppy, and you shaped your answer around it.

Re-read against the physics we are now actually signing, our own measured doctrine table
says the opposite:

```
doctrine          police pts   capture     thief pts
registered_v3       19.214      94.8%        9.736      <- your physics
subtractive         18.810        -          9.895
book_v1             18.940      92.9%        9.877
```

Your physics is our **strongest police doctrine of the five we ship**, and the police
half is the 20-point half. So we are not conceding anything by playing it and you should
not read our earlier paragraph as a grievance we are swallowing. If you do ever ship a
subtractive emitter we would still be glad to see it — but for this pairing, and for the
counted series, your physics is a fine place for us to stand. We would rather correct
this now than have it sit in the record as a favour you did us.

---

## B) SCENT — adopted. The lock binds.

Your bytes verify. We recomputed your document independently and got your hash exactly:

```
ours:   934c220d5bf62acaa3297c6c9d723ea954c220260b02292ca17f6d5daef9f4d9
yours:  934c220d5bf62acaa3297c6c9d723ea954c220260b02292ca17f6d5daef9f4d9   MATCH
```

Your document also round-trips through our canonicaliser byte-for-byte, and your
saturating example reproduces down to the floating-point tail:
`(1 - 0.1) * 0.9 + 0.62 = 1.4300000000000002`, clamped to `0.9`. That last digit is a
better conformance check than the prose, and we are glad you put it in the document.

**`multiplicative_book_v1` is now a registered model on our side and it is what we will
declare.** We have also published your document as a lock artifact in our own repo, in
your exact bytes, so anyone can verify it the way we asked you to verify ours:

```
sha256sum docs/locks/scent_multiplicative_book_v1.json
934c220d5bf62acaa3297c6c9d723ea954c220260b02292ca17f6d5daef9f4d9
```

### What we found while doing it, and why it made this cheap

Your physics is **identical** to our `registered_v3`, not merely similar. We checked it
mechanically rather than by reading: same kernel (element for element against our own
constant), same rho, same centre, same clamp, same one-expression update, same
serve-after-update. Our test drives both models over a five-step walk and asserts the
served fields are equal at every step.

So this was a **document registration, not a physics implementation** — the behaviour
already shipped, and the doctrine we had already tuned for that physics applies
unchanged. That is the whole lesson of this exchange, and it is worth saying plainly:
two teams running provably identical physics still refuse each other until one adopts
the other's bytes, because **the lock is over the document and never over the
behaviour**. We now hold both documents for one physics and declare whichever a given
opponent is pinned to. Your constraint was real and it cost us almost nothing to meet.

One trap we hit on the way, in case it is useful to you: our own field-inversion logic
keeps a set of models that serve *after* their own emission, and a newly registered
model that is absent from it is silently given `book_v1`'s one-step lag — no exception,
just an opponent position that is consistently one step stale. It is now derived from
the shared-physics set rather than listed by hand, and there is a test pinning it.

---

## 12) GAME_UID — folded, and you were right in a way we understated

Done. And a correction we owe you, because we told you the opposite last round.

We said: *"`game_uid` is never compared anywhere in our peer — not in the compatibility
gate, not in the result digest, not in the consensus digest,"* and concluded the
divergence was cosmetic and the two rules could harmlessly differ. **The third clause was
wrong.** We had searched for places our code *compares* a uid and found none, which is
true and beside the point: `game_uid` is the second key of our series-consensus document,
so it is hashed into the `consensus_sha` both sides exchange after sub-game 6. Two
different uids means two different digests at the end of a clean 6/6 — and by our own
module's warning, a mismatched consensus digest is indistinguishable from a genuine
disagreement about what was played.

So this was never cosmetic. Had you accepted our "let the two rules differ", we would have
played six good windows and failed to confirm the series, with nothing in the logs to say
why. You pushed on it and you were right to.

Your collision argument is also right on its own terms: a label that reaches the `game_id`
and never the `game_uid` gives two labelled series between the same two teams one uid —
`friendly-1` and `counted-1` would derive the same value, so a counted series could settle
against the digest of the warm-up it replaced. We had `game_uid` derived from the sorted
pair alone and never from the id.

```
game_id  = ahk-yosi-vs-yanell11-friendly-1
game_uid = a0b99406-11d1-384c-823c-0315c9596bab       <- ours now, matching yours
```

We adopted it behind a defaulted argument, so the **unlabelled** seed is byte-identical
to what it was: with no label the material is still `canonical(terms) | lo | hi`, and
every peer that agreed a uid with us before still derives the same one. That is pinned
by a regression test, along with `friendly-1` and `counted-1` deriving different uids —
your fix, restated as our test. For the counted series we will re-derive from
`ahk-yosi-vs-yanell11-counted-1` as you said, and cross-check in chat before T.

One thing your change cost us that you should know about, since it is the kind of thing
worth hearing from the other side: we had a unit test asserting the **opposite** rule —
"the label overrides the id but never the uid", on the reasoning that the uid must prove
both peers signed the same terms and a label must not be able to forge that. The terms
half of that reasoning is still true and we kept it as an assertion: the terms remain in
the seed, so no label produces a matching uid against a different constitution. The rest
of it was simply wrong, and it is now inverted with your collision argument written into
it as the reason.

---

## YOUR OTHER ITEMS

- **A) Turn order** — noted, and thank you for chasing it into your own handshake. Both
  sides now declare and play thief-first. Commit `e86e88548f8e010cb04afa110f2f7cffcad6ec85`
  recorded on our side.
- **Our commit vector** — confirmed reproduced on your side. Both directions now verified,
  both vectors, both digests. Settlement is closed.
- **9) Capture claims** — threshold on both cops. Your rule (claim only when the belief
  argmax has become the cop's own cell) is the same shape as ours. Thank you for moving
  on it; we did not ask you to and we would have played it either way.
- **17) Patience** — matched: 1000s opening, 1000s per-window re-handshake, 180s per turn,
  ~40s reconnect margin, 600s consensus linger.
- **Everything in your AGREED block** — agreed, nothing outstanding from us.

---

## WHAT WE ARE RUNNING

```
scent model          multiplicative_book_v1   (934c220d...)
doctrine             the one already tuned for this physics - unchanged
setting              Haifa
dialect              reference-v3
game_id              ahk-yosi-vs-yanell11-friendly-1
game_uid             a0b99406-11d1-384c-823c-0315c9596bab
turn order           thief-first
roles                you thief on 1/3/5, us police on 1/3/5, alternation ON
capture claims       threshold
enclosure            thief concedes; our cop-claims-enclosure OFF
re-handshake         fresh negotiate per window
window re-offers     0
consensus            on, linger 600s
counted_games_played 7   (this friendly is not counted)
our door             one URL, both our roles at it - sent immediately before T
```

---

## WHAT WE NEED TO START

1. Your two tunnel URLs, fresh, held up for the whole run.
2. A proposed time.

That is all. Give us a time and we will be up and idle before it, and say so in chat.
We will run the 30s read-only `tools/list` probe each way first, as agreed.

— ahk-yosi (Ahmad Kaiss, Yosef Shanaa)
apexmediamind@gmail.com
