=== ahk-yosi -> yanell11, round 8 ===

Nell, Yanal — six of six played, every window `Verified OK`. **Your fix works.** The wire
gap between us is closed.

Then the series failed to close, and there are two faults in that: one yours, one ours.
Ours is the worse of the two and we'd rather lead with it.

---

## THE RUN

```
sub-game 1  survival  your thief survived 35   audit Verified OK
sub-game 2  capture   our thief enclosed       audit Verified OK   <- e0542dc
sub-game 3  survival  your thief survived 35   audit Verified OK
sub-game 4  capture   our thief enclosed       audit Verified OK   <- e0542dc
sub-game 5  survival  your thief survived 35   audit Verified OK
sub-game 6  capture   our thief enclosed       audit Verified OK   <- e0542dc

final: ahk-yosi 30, yanell11 90
```

Congratulations — that is a clean sweep and it was not close. Your thief out-survived our
pursuer in all three of its windows, and your cop caged our thief in all three of its own.

**`e0542dc` is proven.** Three separate enclosures, each one settled, filed and advanced
past. The concession that hung you twice — riding a duplicate step number with a commit
you already held — now lands every time. Cold start also worked exactly as intended: your
first agreement claimed `sub-game 1`, which was the tripwire we were watching after the
last run, and it passed.

---

## FAULT 1, AND IT IS OURS: we misread our own watchdog and killed the run early

We told ourselves our peer had frozen. It had not. Correcting it here because the
correction is the useful part.

After window 6 our process entered the series-consensus linger and blocked in
`wait_for_consensus` - waiting the 600s we agreed, for an envelope from a peer that had
already gone. Our watchdog beats only inside the two turn loops, and its timeout is 60s,
so ~60s into a *legitimate* 600s wait it printed:

```
WATCHDOG: main loop frozen; state persisted, shutting down
```

Both halves of that line were wrong. Nothing was frozen - a bounded wait was doing exactly
its job - and nothing shut down either: the callback persists state and returns, leaving
the main loop running. We read it as a hang and stopped the process by hand about four
minutes before the wait would have expired on its own.

Had we left it, `wait_for_consensus` would have returned empty at ~20:48:39, recorded
`confirmed: false`, closed the declaration and **filed the result artifact and
`mutual_signature` from six windows that had all audited `Verified OK`**. The paperwork we
reported as missing was four minutes away. That is on us, not on your disconnect.

Two real defects behind it, both now fixed on our side: the watchdog is disarmed before the
consensus linger (it guards the turn loops, which are the only things that beat, and the
linger is bounded by its own timeout), and that log line no longer claims a shutdown it
never performs. Both are covered by a regression test.

We are flagging it in this much detail because we had already told you our peer could not
file, and that was not true.

## FAULT 2, AND IT IS YOURS: you left immediately after window 6

Your processes exited the instant sub-game 6 closed:

```
20:38:39  Session termination failed: 502
```

Both your doors have been 502 since. This is the one item from our original agreement that
did not hold - *"processes stay alive past sub-game 6"* - and it is why the consensus
exchange never began. Even with our freeze fixed, there would have been nobody to exchange
with.

We think these two are independent: yours removed the counterparty, ours removed our own
ability to file regardless. Both need fixing before anything counted.

---

## SO: CONSENSUS IS STILL UNTESTED

Three runs in, the digest exchange remains the one part of the contract neither of us has
ever exercised. It is also the part that matters most for a counted series, because it is
where the folded `game_uid` actually gets used - the `mutual_signature` scope keys on
`game_id`, but the consensus document carries `game_uid` as its second key, which is
precisely why we adopted your labelled derivation.

**What we propose:**

1. **We fix the freeze.** The series must end and file whether or not you are still there:
   a vanished opponent should cost us the confirmation, never the result.
2. **You hold both processes open after window 6** until the consensus envelope has been
   exchanged both ways, or your linger expires. Ours is set to 600s and will wait.
3. **One more friendly**, purely to exercise the close. We do not need six windows for
   that - if your driver can run a short series we are happy with two, or even one. The
   only thing being tested is that both sides file, exchange `consensus_sha`, and agree.

If you would rather go straight to the counted series once both fixes are in, we would
want one clean consensus exchange first. Everything else is now proven: handshake, terms,
scent lock, commit digests, result digests, six windows, three enclosures, alternation,
per-window re-handshake, cold start. It is a short list of one.

Nothing else outstanding from our side, and no changes to anything already agreed.

— ahk-yosi (Ahmad Kaiss, Yosef Shanaa)
apexmediamind@gmail.com
