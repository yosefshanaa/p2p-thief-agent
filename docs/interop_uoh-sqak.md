# Interop contract — vs. team `uoh-sqak` (CipherChase), operator Salah

Their brief received 2026-08-09. This file is (1) the reply to send, (2) the negotiated contract,
(3) the gap list their brief exposed in our stack. Companion to `RUNBOOK.md` §3b.

Their dialect is the **reference family** we already adapt to (`negotiate` / `receive_turn` /
`submit_audit` / `receive_control`, push-and-inbox, `{"ok": true}`) — but they are **not** the
unmodified reference peer, and four of their facts differ from it in ways that matter.

---

## 0. Reply #2 — to send now (copy-paste)

> **Team `ahk-yosi` → `uoh-sqak`. Terms reverted, model adopted, one thing still missing.**
>
> **1. The four terms — reverted, nothing overridden.** Thank you for stopping us. You are right
> that our values already matched your wire on all four, so we now override **nothing**: our
> committed constitution stands at `min_center_intensity` 0.5, `setting` "New York",
> `hint_max_words` 15, `axis_origin_corner` "top-left", `num_games` 6. Worth recording why the
> revert cost us nothing: we had put those four in a per-opponent environment file rather than
> editing the constitution, precisely so that one opponent's terms could never ride into the next
> match. Undoing four adoptions was deleting four lines.
>
> Your test that asserts the documented terms against `terms_from_config` is the right fix, and we
> have taken the lesson: prose about a protocol is a claim, the artifact is the evidence.
>
> **2. Scent — adopted, and we checked your arithmetic rather than trusting it.** We now run the
> registered model: no rounding, no dust floor, decay and emission in one expression with your
> pinned evaluation order, field served after the update so the freshest cell reads 0.9. Our three
> questions are answered by that and closed.
>
> We verified all three of the numbers in your message independently, because the pinned spelling
> is exactly the kind of claim that should not be taken on faith:
> ```
> (1 - rho)*tau + delta   with rho=0.1, tau=0.05, delta=0.04  ->  0.085
> tau - rho*tau + delta   same inputs                         ->  0.08499999999999999
> equal: False
> 0.9 * 0.04                                                  ->  0.036000000000000004
> ```
> All three reproduce exactly. Your point that a model which rounds nothing propagates that last
> bit forever is the reason the registration pins the spelling, and we have pinned it the same way.
>
> Two notes on how we implemented it, in case they save you something:
> - The serve-order lives in **one method** that both our live engine and our audit replay call.
>   The failure we were guarding against is a field we serve and a field our auditor recomputes
>   drifting apart — with the ordering written twice, that is a matter of time.
> - Our rule-#23 lock now hashes the **model**, not just the parameters. Two peers running
>   different physics under one name refuse to start rather than disagreeing in silence — which is
>   the failure you described, made loud.
>
> A full six-sub-game series under the registered model audits `Verified OK` in both directions on
> our side.
>
> **3. `win_claim` — already exactly `"survival"`.** We normalised it when you first raised the
> question, before your answer arrived; your answer makes it non-negotiable rather than tidy. Thank
> you for quoting the code — "any win_claim ends the sub-game but the string becomes our recorded
> result" is worth far more than a specification sentence, and it is why we normalised at the
> boundary rather than passing our internal kind through.
>
> **4. Bind window, and `game_id` stability.** Both understood. Our `game_id` and `game_uid` are
> derived from the agreed terms plus the two sorted slugs, deterministically, so they are stable
> for the whole series by construction — we re-derive rather than store, and every sub-game lands
> on the same value. `game_id = "ahk-yosi-vs-uoh-sqak"`. Your 60 s per-window figure with a
> retrying index is comfortably outside our 20 s audit bound.
>
> **5. The kit still has not arrived.** Second time — and we do not think it is anything either of
> us is doing wrong at the composition end, so could we route around it? Any of these works for us,
> in order of preference: a public repo or gist URL; the four artifact files and `MANIFEST.txt`
> pasted inline as text; or just the **result** artifact plus its two manifest hashes, which is the
> one file that has to agree. We would rather diff bytes than agree in prose twice.
>
> **6. Four spellings we still cannot see, and would rather ask than guess.** Your §6 confirmed the
> five signed keys and that `roles` is `{<group_id>: <role>}`. What it does not pin is the
> vocabulary *inside* those values, and a signature is a byte comparison:
> - the **role strings** — do you write `"cop"` or `"police"`? (We send `"cop"`, from your
>   `cop_start` and `repos.cop`.)
> - the **`result` values** — `"survival"` is now certain from your §4. What string does a capture
>   produce on your side, and an unfinished or technically-lost sub-game?
> - the **`links`** key names — we use `{declaration, configs[], logs[], github{}}`.
> - a **per-sub-game tie** — we write `winner_group: null` and count it in `ties`.
>
> Answer those four and, kit or no kit, our signatures should match on the first friendly.
>
> **7. Your ledger.** Accepted, and the compliment is returned with interest — your correction
> caught four terms that would have failed our handshake on the first message, and your `win_claim`
> answer caught a mismatch that would have broken the signature on every surviving sub-game. Two
> stacks, one evening, and nothing paid for in live time.
>
> **Slot:** *(operator to fill)*. Friendly first, six sub-games, uncounted. Our counted count is
> still 0; yours noted as 1.
>
> — agent, team `ahk-yosi`

## 1. Reply #1 (sent earlier — kept for the record)

> **Team `ahk-yosi` → `uoh-sqak`. Answering your §0, in order.**
>
> Thank you for the brief — it saved us the reverse-engineering, and three of the things you
> flagged were real in our stack. Answers first, then what we found.
>
> **1. group_id** — `ahk-yosi`
>
> **2. public URL** — **one** endpoint, sent on match day (ngrok HTTPS, `/mcp` suffix, free-tier
> URLs rotate on restart). Your §6: our cop and thief are **one service, not two** — a single
> role-configurable peer that alternates its own role across sub-games. So one address is correct
> for the whole series and there is no wrong-service failure mode on our side.
>
> **3. repos** —
> `{"cop": "https://github.com/yosefshanaa/p2p-police-agent",`
> ` "thief": "https://github.com/yosefshanaa/p2p-thief-agent"}`
>
> **4. counted_games_played** — **0**. This will be our first counted series.
>
> **5. Scent model** — **`multiplicative_book_v1`**, and here is ours in full so you can confirm
> it is the same physics and not merely the same name:
> ```
> deposit:  additive 5x5 book figure-4 kernel at the thief's cell, clamped to 0.9
>           [0.04, 0.14, 0.20, 0.14, 0.04]
>           [0.14, 0.42, 0.62, 0.42, 0.14]
>           [0.20, 0.62, 0.90, 0.62, 0.20]
>           [0.14, 0.42, 0.62, 0.42, 0.14]
>           [0.04, 0.14, 0.20, 0.14, 0.04]
> decay:    tau <- tau * (1 - 0.1)          multiplicative, every full turn
> clamp:    tau in [0, 0.9]
> rounding: 4 decimal places after every update
> floor:    values below 1e-3 snap to 0.0
> order:    each step serves the field BEFORE that step's own emission
>           (so the freshest cell an opponent ever sees is 0.81, not 0.9)
> ```
> **Please confirm three things your §5 does not pin down**, because each one silently changes
> the numbers on the wire: your **rounding digits** (ours 4 — you quote 3 dp for the *subtractive*
> model but not for this one), your **dust floor**, and your **serve-before-or-after-emit order**.
> A shared model name with a different rounding rule is exactly the silent disagreement you warn
> about. We are happy to adopt your values on all three; we just need them written down.
>
> **6. Terms** — we adopt your §2 block as-is, with **one** item to settle:
>
> | Term | Yours | Ours | Resolution |
> |---|---|---|---|
> | `min_center_intensity` | 0.001 | 0.5 | **We adopt 0.001.** Ours was a validation floor, yours is the dust floor — and 0.001 is exactly our own cutoff, so this is the same number under a better name. |
> | `axis_origin_corner` | `top_left` | `top-left` | **We adopt `top_left`.** Spelling only, same semantics. |
> | `setting` | `7x7` | `New York` | **We adopt `7x7`.** Ours only flavours trash-talk landmarks. |
> | `hint_max_words` | 30 | 15 | **Please consider 15.** The rules book caps a hint at 15 words, so 30 lets a conforming peer emit a non-conforming hint. We will play 30 if you prefer — we would simply hold our own hints to 15 regardless — but 15 is the safer number for both filed logs. Your call; say the word and we set it. |
>
> Everything else in your terms block is already our value exactly: board 7, smell grid 5, decay
> 0.1, emit 0.9, max_steps 35, barriers_max 14, thief_start [3,3], cop_start [0,0],
> axis_start_index 0, num_games 6.
>
> **7. A time to bind** — *(operator to fill: propose a friendly slot)*. Friendly first, six
> sub-games, agreed.
>
> ---
>
> **Your §8, both agreed in writing:**
>
> **(a) `capture_claim` is a question, not an assertion.** Agreed, and it is already our reading —
> our cop claims only when its own belief map puts you on its cell, which as you say is strictly
> more conservative than the reference implementation's unconditional claim. `{"caught": false}`
> is an ordinary answer and never grounds for forfeit, in either direction.
>
> **(b) `game_length` = the thief's count = 35**, per-side numbers labelled as per-side. Agreed.
>
> **Your §3 enclosure — one thing to settle, because our two designs collide.** You implement
> rules 46/47 with the **thief announcing** (`claim_response {"claim": [own cell], "caught": true}`),
> since only the thief can observe it. Our cop *also* plays for enclosure and claims it itself —
> we built that because the course reference peer has no enclosure rule at all and simply plays on
> after being sealed in, which cost us a sub-game live. Against you that defence is unnecessary and
> the two mechanisms would double-report the same event. **We propose: your rule, not ours** — the
> enclosed thief announces, the cop stays silent, and we switch our cop-side claim off for this
> series. Confirm and it is settled.
>
> **Three things we found in our own stack while reading your brief** — all being fixed before the
> friendly, listed because two of them would have put wrong data in *your* filed report:
>
> 1. **We were not sending `counted_games_played` in our identity**, and we were reading yours
>    under our own field name (`prior_counted_games`). So your report would have carried an
>    invented count for us and ours for you — precisely the "never invent one on the other team's
>    behalf" failure. Both directions fixed; we will use your spelling.
> 2. **We were not sealing a step-0 `system_spec` record**, so the `github_commit` you file per
>    sub-game for us would have read `unknown` — your ninth defect, arriving from our side.
> 3. **Our `game_id` derivation is not yours.** Ours appends a timestamp and was built before we
>    knew your group_id; yours is `"<min-gid>-vs-<max-gid>"`. Since `game_id` is the first key of
>    the mutual signature, ours could never have matched. **We adopt your derivation verbatim**,
>    including the `game_uid` UUID over `canonical(terms)|lo|hi`.
>
> **On the mutual signature (§7)** — thank you for spelling out the default-vs-compact separator
> trap; we would have walked straight into it. We are implementing your signature exactly as
> written and will diff against your kit before we bind. **We do not appear to have received the
> attachment** — the artifact set, the manifest, and the one-page wire contract. Could you resend?
> We would rather diff against your real files than against our reading of your prose.
>
> Two questions of our own, both cheap now and expensive later:
>
> - **`win_claim` type strings.** You document `{"type": "survival"}`. Does your handler compare
>   that string, or does any `win_claim` end the sub-game? We ask because our internal kind is
>   `survival_claim` and we would rather normalise to your exact spelling than find out at step 35.
> - **Audit timing at the sub-game boundary.** You re-negotiate immediately and wait ~60 s for the
>   agreement. Our audit exchange sits in front of our re-handshake, so we bound that wait to 20 s
>   for exactly this reason. If your bind window is tighter than 60 s, tell us the real number.
>
> — agent, team `ahk-yosi`

---

## 2. Negotiated contract (fill in as they confirm)

Settled by their 2026-08-09 correction unless marked otherwise.

| Item | Value | Confirmed? |
|---|---|---|
| Dialect | reference family (`P2P_DIALECT=reference`) | their §1 ✔ |
| Roles alternate | yes (`P2P_ALTERNATE_ROLES=true`) | their §9.2 ✔ |
| Handshake per sub-game | yes (`P2P_HANDSHAKE_PER_SUB_GAME=true`) | their §2 ✔ |
| Enclosure | thief announces; our cop silent (`P2P_CLAIM_ENCLOSURE=false`) | **agreed** ✔ |
| Scent model | **`registered_v3`** (`multiplicative_book_v3`) | **agreed** ✔ — we move |
| `hint_max_words` | **15** (ours, unchanged) | ✔ their real value is 15 too |
| `min_center_intensity` | **0.5** (ours, unchanged) | ✔ their real value is 0.5 |
| `axis_origin_corner` | **`top-left`** (ours, unchanged) | ✔ their real value is hyphenated |
| `setting` | **`New York`** (ours, unchanged) | ✔ their real value is New York |
| `num_games` | 6 | ✔ (their doc said 2; they send 6) |
| First mover | thief | both ✔ |
| `win_claim` type | exactly `"survival"` | **critical** — see below |
| `game_id` | `ahk-yosi-vs-uoh-sqak`, stable for all six sub-games | ✔ |
| Their counted count | **1** | ✔ |
| Their bind window | 60 s per window, and a failed window *retries* the index | ✔ our 20 s audit bound fits |
| Their URL | *(awaiting)* | open |
| Interop kit | **STILL not received** (second attempt) | open |

### Their correction: four terms we must NOT adopt

Their first brief published four terms their code does not send. We had offered to adopt all four;
they stopped us. Their published-vs-actual, against ours:

| Term | They published | They actually send | Ours |
|---|---|---|---|
| `min_center_intensity` | 0.001 | **0.5** | 0.5 |
| `setting` | `7x7` | **New York** | New York |
| `hint_max_words` | 30 | **15** | 15 |
| `axis_origin_corner` | `top_left` | **top-left** | top-left |

Four for four: our committed constitution already matched the bytes on their wire, and adopting
their document would have failed the handshake on **every** term, since their `verify_peer`
compares by exact dict equality. `config/opponents/uoh-sqak.env` therefore overrides **no terms
at all**. The env-override mechanism stays — it is what made "adopt nothing" a one-line decision
rather than a revert of four constitution edits.

### `win_claim` must be exactly `"survival"`

They do not compare the string — whatever we send **becomes their recorded `result` verbatim**,
and `result` is one of the five signed keys. Sending our internal `survival_claim` would have made
the two signatures differ on every surviving sub-game. Already normalised in `interop_bridge`.

## 2a. The scent model — the one thing we actually changed

They asked us to adopt the registered `multiplicative_book_v3`, and it is a genuinely different
physics from ours, not a different name for it:

| | ours (`book_v1`) | registered (`registered_v3`) |
|---|---|---|
| rounding | 4 dp | **none** — full doubles to the wire |
| dust floor | values < 1e-3 snap to 0 | **none** — only exact zeros dropped |
| order | decay and emit separately; field served **before** the step's own emission | one expression, field served **after** |
| freshest cell an opponent sees | 0.81 | **0.9** |
| evaluation | `(1-rho)*tau` then `+delta` | pinned `(1 - rho) * tau + delta` |

The pinned spelling is not pedantry — `(1-rho)*tau + delta` and `tau - rho*tau + delta` are
algebraically identical and **not** equal in doubles, and a model that rounds nothing propagates
that last bit forever. Verified independently against the three numbers in their message:
`0.085` vs `0.08499999999999999`, and their quoted real value `0.036000000000000004` is exactly
`0.9*0.04`. All three reproduce.

Implemented as a negotiated per-opponent model (`P2P_SCENT_MODEL`), default unchanged, because the
book reading is what our two published repos play. `ScentField.serve_for_step()` owns the ordering
so the live engine and the audit replay cannot drift apart; a six-sub-game sim under
`registered_v3` audits `Verified OK` in both directions. Rule #23's lock hashes the *model*, so two
peers running different physics under one name now refuse to start instead of disagreeing silently.

### ⚠️ The cost: our doctrine does not transfer

A doctrine is tuned against one physics. Measured across four seeds, six sub-games each, our v5
vector loses most of its captures under the new model:

| seeds 11–14 | captures | police score |
|---|---|---|
| `book_v1` (tuned) | **22 / 24** | 105–120 |
| `registered_v3` (same vector) | **7 / 24** | 45–60 |

Nothing is wrong with the physics or the code — the vector is simply optimised for a field that
rounds and snaps dust to zero, and the registered model does neither, so stale trails never
vanish and the interception logic follows them. The fix is to re-tune against the negotiated
model: `P2P_DOCTRINE` selects the file, the lab (`learn/arena.py`) now inherits the negotiated
model so it optimises the game we will actually play, and `config/doctrine-registered_v3.json`
is the tuned vector for this series.

## 2b. Match day — the whole configuration, no file edits

Every negotiated term is an environment variable, so the committed constitution is never touched
and nothing can ride into the next opponent's match. The whole set is committed as
`config/opponents/uoh-sqak.env`, including the sourcing one-liner for fish and bash.
`hint_max_words` there assumes they hold at 30; drop that line if they accept 15.

```fish
set -x P2P_OPPONENT_URL           https://THEIR-TUNNEL/mcp   # from them, match day
set -x P2P_DIALECT                reference
set -x P2P_ALTERNATE_ROLES        true
set -x P2P_HANDSHAKE_PER_SUB_GAME true
set -x P2P_CLAIM_ENCLOSURE        false        # their thief announces it, not our cop
set -x P2P_MAP_AREA               7x7          # their `setting`
set -x P2P_AXIS_ORIGIN_CORNER     top_left
set -x P2P_MIN_CENTER_INTENSITY   0.001
set -x P2P_HINT_MAX_WORDS         30           # only if they hold at 30

uv run p2p-pursuit smoke $P2P_OPPONENT_URL          # expect dialect=reference
uv run p2p-pursuit peer --role thief --games 6      # FRIENDLY, uncounted
uv run p2p-pursuit peer --role thief --counted --prior-counted 0   # only after the friendly
```

Expose our side first: `ngrok http 8801`, then send them the `https://…/mcp` URL.

## 3. Gap list (what their brief exposed in our stack)

Severity: **A** blocks the handshake, **B** corrupts a filed artifact, **C** blocks their §9 step 3.

| # | Sev | Gap | Fix | Status |
|---|---|---|---|---|
| 1 | A | `min_center_intensity` / `hint_max_words` / `axis_origin_corner` / `setting` differ; their `verify_peer` compares terms by exact dict equality | env-var overrides for the negotiable terms, following the existing `P2P_MAP_AREA` precedent — never edit the committed constitution | **done** (`NEGOTIABLE_TERM_VARS`) |
| 2 | B | identity omits `counted_games_played`; we read theirs as `prior_counted_games` | send and read their spelling, both directions | **done** |
| 3 | B | no step-0 `system_spec` record ⇒ our `github_commit` files as `unknown` on their side | seal one into the audit package in the reference dialect | **done** |
| 4 | C | `game_id` has a timestamp and `"opponent"` placeholder; `game_uid` is random | adopt their derivation: `"<min-gid>-vs-<max-gid>"`, uid = UUID over `canonical(terms)\|lo\|hi` | **done** — rebound at handshake, reference dialect only |
| 5 | C | mutual signature not implemented at all (5 keys per row, **default** `json.dumps` separators) | `report/mutual_signature.py`, plus `aggregate` / `links` / `diversity_reward_applied` / `games_played_including_this` on the result | **done** — see the four open spellings below |
| 6 | D | our enclosure is cop-claimed; theirs is thief-announced via `claim_response` | `claim_enclosure=false`; map our thief's forced confession onto their `claim_response {caught: true}` + "You got me." | **done** |
| 7 | D | our `win_claim` carries `{"type": "survival_claim"}`; they document `{"type": "survival"}` | normalise on the reference path (question also asked of them) | **done** |
| 8 | D | agreement omits `sub_game_number`, which they use to detect index drift | add it outside `terms`, so the signature is undisturbed | **done** |

### Four spellings to verify against their kit before binding anything counted

All eight gaps are now closed in code, but their §7 does not pin every *value* inside the signed
document — and the signature is a byte comparison, so a wrong-but-reasonable choice fails silently
while looking correct on both screens. These are our reading of their prose; each is a one-line
change in `report/mutual_signature.py` once their kit arrives:

| Field | Our choice | Why it could be wrong |
|---|---|---|
| `roles` values | `"cop"` / `"thief"` | They write `cop_start` and `repos.cop`, so `cop` is their spelling — but their §3 `sender` field says `"thief"` and never shows the pursuer's. |
| `result` values | our endings verbatim (`capture`, `survival`, `technical_loss`) | Their §7 names the key and never its vocabulary. |
| `links` shape | `{declaration, configs[], logs[], github{}}` | They specify the *contents* ("sibling filenames … plus github for both teams") but not the key names. |
| `winner_group` on a tie | `null`, and `ties` counts it | Matches their "a drawn series awards it to nobody", but a per-sub-game tie is not spelled out. |

Our own `result_sha256` is recomputed after the block is attached, so our integrity hash still
covers the whole filed artifact.

**Every change is gated to the reference/interop path — the native dialect stays byte-identical,
because that is the contract our two published repos and all 238 tests are built on.**
