# Reply — ahk-yosi → MaRs-777 — 2026-08-24 (rev 4)

Mohamed, Rawey — **§16 is in.** Both halves, tested, pushed to all three repos.

```
cd05e267c108cb73b07df1dd9f10f3f8d335abc5
```

Everything below is read out of that commit. Slot proposal at the end.

---

## 1 — the projection, and the proof that our claim was true

We said your `series_consensus_sha256` was our `mutual_signature` carried in the
other envelope. That was an assertion when we made it. Here it is as a
measurement, from the same six-row series:

```
mutual_signature (what we already file) : aeb715ecef0047de627c1ee8da28d17735c6878bfb61ab5b1bb269ba4a5808d2
consensus sha    (what we now send)     : aeb715ecef0047de627c1ee8da28d17735c6878bfb61ab5b1bb269ba4a5808d2
identical: True — and the two documents compare equal, not merely their digests
```

So on any **untied** series we were already computing your number and sending the
other one. The tie award below is the only thing that ever separated them.

The family is negotiated per opponent, not switched globally. Set for you:

```
P2P_CONSENSUS_PROJECTION=signature
```

`{game_id, aggregate, sub_games}` · `json.dumps` defaults, not compact · no
`game_uid`. Our own default family is untouched for every other team.

One deliberate design decision you should know about, because it changes what a
misconfiguration looks like: **an unknown projection name raises where the config
is read.** It does not fall back to our default. A peer configured for a family
we do not implement has to fail at boot, not settle six windows against the wrong
bytes and then report it to you as a disagreement about what was played.

---

## 2 — the tie award, exactly as you specified it

Both your answers are implemented as given:

- **Only when the series totals are level.** Never on a drawn row. A drawn row
  still contributes to `ties` and still carries `winner_group: null`; its score
  stays raw.
- **After**, and into `total_score` alone. `winner_group` and `series_tie` are
  derived from the **raw** totals first; `sub_games_won` and `ties` never see the
  award.

Your instinct to spell out the ordering anyway was right, and here is the proof
it was worth your paragraph: a tied series changes digest depending on whether
the award is applied at all —

```
tied series, award on  : 81dacf3cf8df3036…
tied series, award off : 2bd2c6b7bd1745cf…
```

We would have shipped the second one.

**It is opt-in on our side**, and that is not hedging. The same aggregate builder
feeds our `mutual_signature`, which we have already exchanged and matched with
other teams. Awarding by default would silently move that digest for every tied
series we have ever agreed with anyone — on a rule that only you have put in
writing to us. So the default stays 0, byte-identical to what we shipped, and the
award is passed only by the projection that asks for it. If the award turns out
to be book-universal rather than yours, that is a one-line change later; getting
it wrong in the other direction would break agreements already signed.

---

## 3 — the retry, and a defect our own tests caught

Ours was one attempt with the exception suppressed. It now resends until
acknowledged, inside the 600 s linger, paced at 5 s.

**The first version we wrote was wrong, and we would rather tell you than not.**
It exited as soon as *your* digest arrived. That is a real bug and it is the exact
hazard we were fixing, viewed from the other side: you can settle and answer while
our envelope has never reached you, and stopping there would leave **you** unable
to settle. The two directions are independent. It now runs until **both** halves
are done — ours acknowledged and yours received — or the window closes.

Two consequences worth having in writing:

- A digest we received but could not answer is **returned and recorded**, not
  discarded. Received-but-unanswerable is evidence.
- Our artifact now carries `envelope_delivered`, so a failed settlement
  distinguishes "they never got ours" from "they never sent theirs". Those have
  looked identical in our logs until today.

Your `sender` rule needs nothing from us: we send the wire role held in sub-game
6, and with us opening thief that is **police** — matching your reading.

---

## 4 — your three greeting traps: we trip none of them

Checked rather than assumed, since you were specific:

| your trap | ours |
|---|---|
| no top-level `kind` / `payload` / `request` tool arguments | `negotiate` sends exactly one argument, `{"message": …}` |
| `identity` inside `message` | it is a key of the signed greeting, never a tool argument |
| `strict=True` exact JSON types | `sub_game_number` is an int, `role` is exactly `"police"` / `"thief"`, `nonce` and `signature` are non-empty strings |

Thank you for the `extra="ignore"` explanation and for quoting your own docstring
at us — "tolerated is not trusted: an unknown key reaches no semantic value" is
the right seam and it is why our identity block is safe to send.

**One thing to check on your side.** We send `scent_model_sha256` as a key that
can hold the **empty string** rather than being omitted, if our handshake block is
not yet populated when the greeting is built. You said omission is silence and
that the four lock digests are optional. Is an empty string also silence, or does
`strict=True` treat `""` differently from absent? It will be populated in
practice, but we would rather ask than find out at 20:40.

The Step-0 batch — `github_commits` as an object, `cpu_freq_ghz` as decimal text,
`gpu: false`, `vram_gb` omitted, the `Z` timestamp — is queued for the counted
run-up, where you placed it. Not on tonight's path.

---

## 5 — the slot

Your terms, met. Naming one:

**Tonight, 2026-08-24, 21:00 Israel (18:00 UTC).** Tunnels up 20:40, URLs
confirmed in writing, both probing until the edge clears, start within a minute
of each other.

If that is too tight at your end, **tomorrow 2026-08-25 at 17:00 UTC** — your
original proposal — stands and we will hold ours up for yours. Either suits us;
say which and we will be up twenty minutes ahead.

Our endpoint, unchanged, one URL both roles, reserved static domain, 502 from the
edge while we are down:

```
https://zealous-sliver-gleeful.ngrok-free.dev/mcp
```

Configured against you: `multiplicative_book_v1`, `setting: "Haifa"`,
`game_id = MaRs-777-vs-ahk-yosi`, `game_uid = 5ed16f3b-4e6b-4e9d-65bf-8f5abab699f2`,
no label, threshold claims, our pursuer-side enclosure emitter **off**, both door
vars pointed at your single gateway so our split-peer guard is armed, and
`P2P_CONSENSUS_PROJECTION=signature`.

We open thief. See you at 20:40.

— ahk-yosi (Ahmad & Yosef)
apexmediamind@gmail.com
`cd05e267c108cb73b07df1dd9f10f3f8d335abc5`
