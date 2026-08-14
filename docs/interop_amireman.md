# Interop contract — vs. team `amireman`

Their "P2P Cop–Thief Match Interoperability Guide" + a schema-1.2 agreement JSON naming
`["amireman", "ahk-yosi"]`, both received **2026-08-14**. This file is (1) the reply to send,
(2) the negotiated contract, (3) the gap list their guide exposed in our stack. Companion to
`RUNBOOK.md` §3b and `config/opponents/amireman.env`.

Third opponent, third member of the **reference family** (`negotiate` / `receive_turn` /
`submit_audit` / `receive_control`, push-and-inbox, `{"ok": true}`). Their guide is the most
precise one we have received — it publishes literal derivations rather than prose, and **every
derivation in it reproduced on our side first try**. The gaps below are almost all ours.

---

## 0. What checked out before we changed anything

Verified against their Appendix A/B/C, not taken on trust:

| Their spec | Our code | Result |
|---|---|---|
| 14 signed terms, exact values **and JSON types** | `interop_codec.interop_terms` | key set equal, **14/14 identical** |
| `game_id` = sorted pair joined `"-vs-"` | `game_ids.reference_game_id` | `ahk-yosi-vs-amireman` |
| `game_uid` = UUID over `canonical(terms)\|lo\|hi`, first **16 raw bytes** | `game_ids.reference_game_uid` | `ab6022d2-716a-f5b3-556e-43f70ffa7b09` |
| `commit_of(payload, nonce)` = sha256(`canonical(payload)` + `"\|"` + nonce) | `crypto.reference_commit` | already pinned by the uoh-sqak golden vector |
| canonical JSON = `sort_keys`, `ensure_ascii=False`, `(",", ":")` | `crypto.canonical_bytes` | byte-identical |
| Appendix C consensus object → SHA | new `report/consensus.py` | **`f9777afb…08043f`, reproduced exactly** |
| Appendix E scent kernel + `τ_next = min(0.9, max(0, (1−ρ)τ + δ))` | `domain/scent.py` `book_v1` | same kernel, same expression |
| `win_claim = {"type": "survival"}` (object) | `interop_bridge` | already this shape |
| survival at exactly 35 completed steps | `turn_engine` `my_steps >= survival_threshold` | already exact |

**One term differs, and it is ours to change:** their `setting` is `"Haifa"`; our committed
constitution says `"New York"`. Their `verify_peer` compares terms by equality, so this alone
would have refused every handshake. Handled by a per-opponent config dir, never by editing the
committed file — see §3.

---

## 1. The gap list — what their guide exposed in our stack

Four defects. All four are invisible in a short healthy-looking run and surface at a sub-game
boundary or in the final audit, which in a counted match is unrecoverable. All four are fixed and
tested; each fix is **off by default** and enabled only by `config/opponents/amireman.env`, so
the behaviour every previously-played opponent saw is byte-identical.

### 1.1 Our cop withheld the capture-claim — silently forfeiting captures we earned

Their §5 is emphatic: the claim is *"set by the protocol/runtime layer, **not** chosen by
strategy, and **cannot be suppressed**"* — the Cop's own post-move cell, every turn, including
`STAY` and barrier turns.

Ours **is** chosen by strategy. `police_brain.should_claim()` gates on `claim_threshold = 0.15`,
because in our own dialect a claim discloses our cell and is spent deliberately. Under their
rules that gate is strictly harmful: their thief evaluates condition (A) only against a claim it
actually receives, so **a turn where we step onto their cell without claiming is a capture we
earned and do not get**. Our police went 6/6 against orcai-mj; this is the half that wins.

Fixed by `P2P_ALWAYS_CLAIM=true` → `turn_engine.build_own_step`.

**The trade is symmetric and in our favour.** Their cop must declare its own cell every turn too,
and `turn_engine._answer_claim` already collapses our thief's belief to a *delta* at a claimed
cell. So our thief tracks their cop exactly, every turn, for free — the intel our thief did not
have when it lost 0/6 to orcai-mj's barrier cage.

### 1.2 `--games` rewrote the **signed** `num_games`, breaking their own smoke test

Their §15: *"`--games N` … does **not** change the signed `num_games`, which stays `6`"* — a short
run *"signs the normal six-game terms but plays fewer sub-games by mutual agreement"*.

Ours signed whatever `--games` said. A 2-sub-game compatibility run would have signed
`num_games = 2` against their `6` and been refused as a terms mismatch — **on the very test their
§19 gates the official match behind**, and the failure would have read as a constitution
disagreement rather than a flag.

Fixed by `P2P_SIGNED_NUM_GAMES=6`; `runtime.signed_num_games` now feeds the terms (and therefore
`game_uid`), while `num_games` keeps driving the loop.

### 1.3 The §10/§11 series-consensus exchange did not exist at all

`grep -rn consensus src/ tests/` returned **nothing**. Both halves were missing:

- **The object (§11).** `{game_id, game_uid, sub_games}`, exactly three keys, five group-keyed
  keys per row, compact separators.
- **The exchange (§10.3).** A `submit_audit` envelope with `result_claim = "series_consensus"`,
  `records = []`, `sender` = wire role, `consensus_sha` = the digest; then a short bounded wait
  for theirs, accepted only if all three gate conditions hold.

We had a *neighbouring* thing — `report/mutual_signature.py`, built for uoh-sqak — and it is
**wrong here in three separate ways**, each of which still yields 64 valid hex characters:

| | mutual signature (uoh-sqak) | series consensus (amireman) |
|---|---|---|
| top level | `game_id` / `aggregate` / `sub_games` | `game_id` / `game_uid` / `sub_games`, **no aggregate** |
| encoding | `json.dumps` **defaults** (`", "` / `": "`) | **compact** `(",", ":")` |
| `technical_loss` | aliased to `"timeout"` | a **legal value**, must survive verbatim |

So it is a new module (`report/consensus.py`), not a flag on the old one. Enabled by
`P2P_SERIES_CONSENSUS=true`.

**One more defect fell out of building it.** Their consensus envelope arrives on `submit_audit`,
the same tool as the per-sub-game audits — and it carries no records. Our `on_submit_audit` would
have audited it as a log, written an **empty-log verdict over the last sub-game's real one**, and
turned a clean finished series into a technical loss. It now intercepts the envelope first.

### 1.4 `confirmed` could never be true against any reference peer

Caught by our own end-to-end rehearsal, not by review. The first `confirmed` gate reused
`results.agreement_reached`, which additionally requires the **opponent's verdict of us** — a
value this dialect structurally never returns (their `submit_audit` answers `{"ok": true}` and
keeps its verdict private). It would have pinned `confirmed: false` against a peer that agreed
perfectly.

Their §10.4 clause (a) is each side's own verdict of the log it *received* (`row["audit"]`), and
clause (b) is subsumed by the digest, which already covers every row's result, roles, score and
winner. Gate corrected to `sha_match AND every row Verified OK`.

---

## 2. Rehearsal evidence (local, 2026-08-14)

Two real peers over real FastMCP HTTP, distinct group ids, their full contract
(`reference` + alternate + per-sub-game handshake + `always_claim` + consensus), `--games 2`:

```
run-us   -> 0f9f86773621e965… | match True | confirmed True
    g1 survival  winner=amireman  audit=Verified OK
    g2 survival  winner=ahk-yosi  audit=Verified OK
run-them -> 0f9f86773621e965… | match True | confirmed True
```

Both sides independently derived the **same** digest and exchanged it; `game_uid` came out
`ab6022d2-716a-f5b3-556e-43f70ffa7b09` on both; the sealed config copies carry `"num_games": 6`
while only two sub-games were looped. 313 tests pass, Ruff clean.

This proves our two halves agree with each other. It does **not** prove agreement with *their*
implementation — only the Appendix C reproduction and the smoke test do that.

---

## 3. Launch (both peers, per-opponent config dir)

`setting` must be `"Haifa"` for them and stay `"New York"` for everyone else, and `agreed_between`
names one opponent — neither can live in the committed constitution without riding into the next
team's handshake. So:

```fish
for l in (grep -v '^#' config/opponents/amireman.env); set -x (string split -m1 = $l); end
set -x P2P_OPPONENT_URL https://THEIR-TUNNEL/mcp

uv run p2p-pursuit peer --role police --config-dir config/opponents/amireman/police --games 6
uv run p2p-pursuit peer --role thief  --config-dir config/opponents/amireman/thief  --games 6
```

Committed constitution stays `0061d8f8…dc088`; theirs hashes to `429f4561…77c5e`.

---

## 4. Message to send them (copy-paste)

> **Team `ahk-yosi` → `amireman`.** Thank you for the guide — it is the most precise contract we
> have been sent, and publishing literal derivations rather than prose meant we could check it
> instead of agreeing to it. We reproduced your Appendix C object and its SHA
> (`f9777afbe5b0f720cc644e38634789575cb582ea57eb7867a41bf01d2c08043f`), your `game_uid`
> derivation, and your Appendix E kernel before replying. **We accept the guide as written.**
>
> **Confirmed on our side.** All 14 terms match Appendix A exactly, values and JSON types —
> including `setting: "Haifa"`, which was the one value we had to move (our committed default is
> `"New York"`; it now lives in a per-opponent config so it cannot leak into another match).
> Derived under those terms, both sides should land on:
> ```
> game_id  = ahk-yosi-vs-amireman
> game_uid = ab6022d2-716a-f5b3-556e-43f70ffa7b09
> ```
> Please confirm you derive the same `game_uid` — if it differs, our terms differ in a byte and we
> should find out now rather than at the handshake.
>
> **Four things your guide made us fix**, in case any are useful to you:
> 1. **The capture-claim.** Our cop gated it behind a belief threshold, because in our own dialect
>    a claim discloses our position. Under your §5 that is strictly self-harming — your thief only
>    tests co-location against a claim it receives, so a turn spent standing on the thief without
>    claiming is a capture forfeited. Now unconditional, including `STAY` and barrier turns, with
>    the barrier cell never used as the claim.
> 2. **`--games` moved our signed `num_games`.** Your §15 is right that it must not; ours would
>    have signed `2` against your `6` and failed the compatibility test as a "constitution
>    disagreement". Fixed — a short run signs six and loops two.
> 3. **The §10.3 consensus envelope shares a tool with the per-sub-game audits.** Ours would have
>    audited it as a log, found no records, and written a technical loss over a completed
>    sub-game. Worth checking your own handler distinguishes them by `result_claim` before the
>    envelope, not after.
> 4. We had a consensus object for a *previous* opponent that differs from yours in three ways —
>    spaced separators, an `aggregate` key, and `technical_loss` aliased to `timeout`. Each still
>    produces 64 valid hex characters. Yours is implemented separately rather than as a flag.
>
> **Five questions.**
> 1. **Timeouts — your two documents disagree.** The agreement JSON says
>    `response_timeout_sec: 30` / `watchdog_timeout_sec: 60`; §7 says the per-turn wait should be
>    *"generous (order of a few minutes)"*. We run 180 s per turn. Which governs? A 30 s deadline
>    is a real risk: peer boot alone is ~3 min on our side, so we also need (5) below.
> 2. **Scent serve order.** Your Appendix E pins the kernel and the update expression but not
>    whether a step is served the field **before or after** its own emission. Ours serves
>    pre-emission, so our freshest cell reads **0.81**, not 0.9. One number settles it. Your "what
>    must match" list says this is local, and we are happy either way — we just want it recorded.
> 3. **`game_id` label.** Do you want the derived `ahk-yosi-vs-amireman`, or an agreed label like
>    `G010`? It is inside the consensus hash, so it must be identical and decided before we start.
> 4. **One endpoint or two?** Your `mcp_servers` map allows either. Our last opponent ran separate
>    cop and thief endpoints; we can do either, but need to know which before match day.
> 5. **Cold start.** We propose both peers begin sub-game 1 at an agreed wall-clock time, and that
>    if indices ever disagree mid-series the peer that is **behind joins** the one ahead rather
>    than restarting. Two peers that both advance on failure and both insist on their own index
>    livelock indefinitely — we have measured it against a live opponent.
>
> **Order of play.** We would like the **non-counted smoke test first (§15, `--games 2`, throwaway
> `game_id`, fresh output dir)**, then a **full six-sub-game friendly**, then the counted match.
> The book allows exactly one counted game per pair and it is sealed the moment both reports are
> sent, so anything that breaks at a sub-game boundary should break before then. If you would
> rather go straight from the smoke test to the counted match, say so and we will.
>
> ```
> READY
>
> Group:                ahk-yosi
> Members:              Yosef Shanaa (213314859), Ahmad Kaiss (325811255)
> Cop repo:             https://github.com/yosefshanaa/p2p-police-agent
> Thief repo:           https://github.com/yosefshanaa/p2p-thief-agent
> Cop runtime SHA:      <40-hex HEAD at match time>
> Thief runtime SHA:    <40-hex HEAD at match time>
> Public MCP endpoint:  <Cloudflare quick tunnel, re-shared immediately before the match>
> Starting role:        cop            (complement of yours — your §17 has amireman as thief)
> Agreed game_id:       ahk-yosi-vs-amireman   (or your label — question 3)
>
> 14 signed terms match (Appendix A, incl. max_steps=35, setting="Haifa",
>    hint_max_words=15, scent 5 · 0.1 · 0.9 · 0.5):                 YES
> 35-step survival semantics:                                       YES
> Capture-claim = Cop post-move cell every turn (A/B/C):            YES
> Transport /mcp, no required bearer auth:                          YES
> Canonical consensus object + SHA-256 (Section 11):                YES
> Final audit + explicit series_consensus digest exchange:          YES
> Server stays alive through final audit; graceful shutdown:        YES
> Public endpoint externally reachable (curl-verified):             at match time
> ```
>
> Prior counted games (rule #37): we declare **1**. Both declarations reach the lecturer, so they
> must be truthful.
>
> One operational note, offered rather than asked: we run matches over a **Cloudflare quick
> tunnel** — we measured ngrok's free tier dropping the MCP session mid-sub-game with both peers
> healthy, where Cloudflare finished with `Verified OK` on both sides. Quick-tunnel URLs rotate on
> restart, so we will re-share ours immediately before the match and after any restart.

---

## 4b. Exchanged at match time

**Their runtime SHAs** (received 2026-08-14, both valid 40-hex):

```
amireman police:  cc26a88a636351bc4fefd050b0aeea055b3f1cc1
amireman thief:   2118c3d1e05019b359b9403d616fff87d6487c40
```

**Updated before DEMO4** (received 2026-08-14, after their interop fixes):

```
amireman thief:   05f25f183e4e96566ff598744474764b73c18c32   <- superseded below
amireman police:  cc26a88a636351bc4fefd050b0aeea055b3f1cc1   <- "unchanged"
```

**Settled, and it answers the question below** (received 2026-08-14, third message):

```
amireman UNIFIED runtime SHA (all 6 sub-games, both roles, on the wire):
                  e1622992b46e7366c7ca10650d3f82c560a9db21
amireman police REPO SHA (published, not advertised):
                  cc26a88a636351bc4fefd050b0aeea055b3f1cc1
```

So `cc26a88a…` is a **repo** HEAD, never a wire value - which is exactly why it never
appeared in their revealed records, and exactly the shape we run ourselves (one runtime
advertising one commit; two published repos with their own HEADs). One runtime covers
both roles on their side too, so the DEMO1 concern about an unpatched Police half is
closed.

**They fixed the receive side.** They now bucket our incoming audit explicitly by
`sub_game_number`, which is the half our own fix cannot supply (§4d, "what is still on
their side"). Verified against our real code path 2026-08-14 - the envelope we emit is
`['records', 'result_claim', 'sender', 'sub_game', 'sub_game_number']` with the index on
the envelope *and* mirrored in every record payload, so either bucketing path works.

**What their peer has actually declared on the wire, per sub-game, is ONE commit for
BOTH roles** - read out of `github_commit` in their own revealed records:

| run | their role on 1/3/5 (thief) | their role on 2/4/6 (police) |
|---|---|---|
| DEMO1 | `2118c3d1e050` | *no audit package sent at all* |
| DEMO2 | `bb0352613990` | `bb0352613990` (g04 no package) |

So `cc26a88a…` has **never appeared on our wire, in either demo**, and in DEMO2 their
police-role records declared the same commit as their thief-role records. Their
"police SHA unchanged" is therefore either a publication convention over a single
runtime, or two processes of which the police one has been declaring the other's
commit. Ask before DEMO4 - see the reply in §4d.

**We do not validate it in code.** `negotiation.check_compatibility` compares
`config_sha256` and `scent_model_sha256` and nothing else; their commit is *recorded*
(declaration, result rows, and their revealed step-0 record) but never compared against
an expected value. "Use the new SHA for audit validation" is, on our side, a ledger
entry - not an automated gate. Adding an optional expected-SHA warning is a one-flag
change if we decide we want it before G011.

Their §3 binds each side's commit inside the `identity` block (`git_commit_hash` ==
`github_commit`), so these are what their peer should declare on the wire. Worth a glance at the
first handshake: an identity whose commit does not match what they sent here means one side is
running something other than what it published.

**Our endpoint** — one tunnel, not two. Roles alternate inside a single six-sub-game series, so
one peer on port 8802 serves both roles across the series and `mcp_servers` names the same URL
for `cop` and `thief`. Quick-tunnel URLs rotate on restart, so this is re-shared at match time.

## 4c. Settled 2026-08-14, and the demo they asked for

**Answered by them:**
- **Per-turn timeout = 180 s.** The `response_timeout_sec: 30` / `watchdog_timeout_sec: 60` in
  their agreement JSON are local network/watchdog config and **not** part of the 14 signed terms.
  Our committed `turn_timeout_seconds = 180` stands; no override needed.
- **Scent serve order:** they accept our pre-emission serve (freshest cell **0.81**) as a local
  implementation detail. The four signed scent terms and the `{"r,c": intensity}` wire shape are
  unchanged, so `book_v1` stands.

**They declined the §15 two-game smoke test** and asked to go straight to a **full six-game
non-counted demo**:

```
game_id  = AHK-DEMO1          (mutually agreed label, NOT the derived id)
game_uid = ab6022d2-716a-f5b3-556e-43f70ffa7b09   (never overridden)
6 sub-games, NOT counted, no lecturer email
amireman starts Thief; ahk-yosi starts Cop; full alternation, audits, final consensus
```

The counted match that follows will be **G011**.

**This forced a fifth fix.** Their §3 allows a `game_id` label and warns it is part of the
consensus hash — and we had no override at all (`grep P2P_GAME_ID src/` was empty). We would have
computed `ahk-yosi-vs-amireman` against their `AHK-DEMO1` and produced a different digest at the
final exchange: a cleanly-played six-game series failing at precisely the step the demo exists to
prove. Now `P2P_GAME_ID`, with the uid deliberately left underived-from-it.

Rehearsed locally under the label: `game_id=AHK-DEMO1` and
`uid=ab6022d2-716a-f5b3-556e-43f70ffa7b09` on both peers, digests equal, `confirmed: true`.

## 4d. AHK-DEMO3: their audit of us failed, and it was ours

Their report after DEMO3, per sub-game from their chair:

| | live commits they received from us | of those, revealed | records in the package they filed |
|---|---|---|---|
| game 5 | 14 | **0** | — (first failure `binding_received_in_play`) |
| game 6 | 35 | **0** | **15**, one binding to a *game 5* commit |

Plus: "role labels appear inverted".

### The cause — not hashing, bucketing

Every record we sent reproduced its own commitment. `p2p-pursuit verify --dir` over the
archived DEMO2 artifacts confirms it on all six sub-games, both directions:

```
g01 police  34 records /  34 sent  ours=OK   theirs=OK
…
g06 thief   70 records /  70 sent  ours=OK   theirs=OK
[verify] our reveal binds: True; theirs: True (5 received)
```

What was wrong is the **index the package was filed under**. Our `submit_audit` envelope was
`{sender, records, result_claim}` — it named no sub-game, so the only way to file it is *by when
it arrives*, and the two peers do not cross a boundary together:

- `finish_sub_game` sends our package, then **waits** up to `REHANDSHAKE_AUDIT_WAIT` (20 s) for
  theirs before advancing. Theirs arrives while we are still on `n`, so we file it correctly —
  which is why `mine_of_them` read `Verified OK` all series and hid the other direction entirely.
- Their peer does not wait. It sends its package and moves to `n+1` immediately, and in the
  capture sub-games it reaches the ending *first* (we learn of it from their `claim_response`).
  Our package for `n` therefore lands in their `n+1` bucket, every time.

Every symptom they reported falls out of that one off-by-one:

- 0 of N bind — they are checking our sub-game `n` records against sub-game `n+1` commitments.
- 15 records where 35 were expected — that is our **game 5** package (14 records + the step-0
  system spec) filed as their game 6.
- "one revealed game-6 commit matches a live commit from game 5" — all of them do.
- **"role labels appear inverted"** — roles alternate, so a package read one index late is
  always the opposite role. This is the tell that dates the defect exactly.

### Six fixes

| # | Defect | Fix |
|---|---|---|
| 1 | the envelope named no sub-game | `sub_game` **and** `sub_game_number` on the envelope; every sealed record mirrors both spellings, so it can also be bucketed by content |
| 2 | the package was read off the running engine | frozen into `engine.audit_ledger` the instant the sub-game ends — `my_records` is emptied at the boundary, and an inbound turn can cross it before we do |
| 3 | `audit_package` reported `engine.role` | the package carries the role **frozen at play time**; after a swap it was reporting the new role for the old sub-game's records |
| 4 | `reference_records` **re-derived** every commit | the live commitment is revealed; recomputation is kept only as a comparison, so divergence is a loud error instead of a package that passes its own check and binds to nothing |
| 5 | `_system_spec_record` minted a fresh nonce **per call** | sealed once per sub-game and cached; a retried `submit_audit` was revealing one claim under two commitments |
| 6 | `_flush_terminal` replayed `_last_turn` across a boundary | refuses to replay a settled sub-game's commitment into a live one |

We also stopped filing *their* reveal by arrival: `_declared_sub_game` reads the envelope, then
the records, and only then falls back to our own index.

### Verification

- **Self-check before sending** (`interop_audit.verify_outgoing_reveal`), run inside
  `bridge.audit` on every package and filed into the log artifact as `audit.my_reveal_binds`.
- **Offline re-check** of any played match: `uv run p2p-pursuit verify --dir <match dir>`.
- **Six-sub-game acceptance**, two real peers over real FastMCP HTTP, their full contract
  (`reference` + alternate + per-sub-game handshake + `always_claim` + consensus), 2026-08-14:
  6/6 `Verified OK` both sides, every package filed under its own index, roles alternating
  correctly, `series consensus 36bba3ff65ae… match=True confirmed=True` on both peers, zero
  warnings. 333 tests pass, Ruff clean.

### What is still on their side

Fix 1 only helps a receiver that **reads** one of the fields. If their `submit_audit` still files
by arrival and ignores both the envelope keys and `sub_game_number` in the payloads, the
off-by-one comes straight back — our records will be right and filed wrong again. This is the one
item to confirm with them before DEMO4 rather than after.

### Reply to send them (copy-paste)

> **`ahk-yosi` → `amireman`.** Your diagnosis is right and the defect is ours. Thank you for
> reporting it per sub-game with the counts — that is what made it findable.
>
> **It was not our hashing.** Every record we revealed does reproduce its own commitment; we
> re-checked the archived DEMO2 artifacts offline and all six sub-games bind in both directions.
> What was wrong is the **sub-game our package was filed under**.
>
> Our `submit_audit` envelope was `{sender, records, result_claim}` and **named no sub-game**, so
> the only way to file it is by when it arrives — and we do not cross the boundary together. Our
> peer sends its package and then waits up to 20 s for yours before advancing, so yours always
> landed while we were still on `n` and we filed it correctly (which is why our side read
> `Verified OK` all series and never showed us the other direction). Yours advances immediately,
> and in the capture sub-games it reaches the ending first. Our sub-game `n` reveal therefore
> landed in your `n+1` bucket, every time.
>
> That single off-by-one produces everything you measured: 0-of-N binding; the 15 records you got
> for game 6 are our **game 5** package (14 records + our step-0 system-spec record); the game-5
> commit you spotted is not the only one, they all are; and **the inverted role labels are the
> tell** — roles alternate, so a package read one index late is always the opposite role.
>
> **What we changed:**
> 1. The envelope now carries **`sub_game` and `sub_game_number`**, and every sealed record
>    mirrors both spellings inside the payload — so you can bucket by envelope or by content.
> 2. The package is **frozen the instant a sub-game ends**, not read off the running engine
>    afterwards. Your first turn of `n+1` could reach us before we had taken it.
> 3. The package carries the **role that played that sub-game**, not the role we hold now.
> 4. We reveal the **commitment we actually sent**, instead of re-deriving it at audit time.
>    Re-deriving is what let a broken package pass its own verification.
> 5. Our step-0 system-spec record is **sealed once per sub-game**, not re-minted per call — a
>    retried `submit_audit` was revealing one claim under two commitments.
> 6. A terminal win claim can no longer ride a **previous** sub-game's turn message.
>
> We also stopped filing *your* reveal by arrival: we read your envelope, then your records'
> `sub_game_number`, and only then fall back to our own index.
>
> **Verified locally, as you asked.** Before every `submit_audit` we now run your check against
> our own package — for each commitment sent in play, a revealed record whose
> `sha256(canonical(payload) + "|" + nonce)` reproduces it exactly, and nothing from another
> sub-game — and file the result into our log artifact. It is also runnable offline over any
> played match: `p2p-pursuit verify --dir <match dir>`. A full six-sub-game run under your
> contract, two peers over real HTTP: 6/6 `Verified OK` both sides, every package filed under its
> own index, consensus digests equal, `confirmed: true`.
>
> **One thing we cannot fix from our side.** The envelope only helps if your `submit_audit` reads
> it. If it still files by arrival and ignores both the envelope keys and `sub_game_number` in the
> payloads, the same off-by-one returns with our records correct and filed wrong again. Please
> confirm which of the two you will bucket on. If extra envelope keys are a problem for your
> handler, say so and we will drop them — the index is in every payload either way.
>
> **Next run:** `game_id = AHK-DEMO4` (your §13 makes a completed series immutable, so the label
> has to change), same terms, `game_uid` unchanged at
> `ab6022d2-716a-f5b3-556e-43f70ffa7b09`. We will send our runtime SHAs and tunnel URL
> immediately before we start. Ready when you are.

## 5. Still open before anything counted

- [ ] Their answers to the five questions above — **(1) the timeout contradiction is the blocking
      one**; a 30 s per-turn deadline against our ~3 min peer boot needs a coordinated start.
- [ ] Their live `/mcp` URL, repo URLs, 40-hex HEADs, member list.
- [ ] Confirm they derive `game_uid = ab6022d2-716a-f5b3-556e-43f70ffa7b09`.
- [ ] §15 smoke test (`--games 2`, both sides same N) — this is the first thing that tests our
      four fixes against *their* implementation rather than against our own second peer.
- [ ] Remove `P2P_EMAIL_MODE=draft` **only** at the moment of the counted launch. amireman is a
      different opponent from orcai-mj, so filing against them is legitimate — but a friendly
      report risks being read as the one counted encounter.
- [ ] Their §13: completed sub-games are immutable, and a failed consensus is never repaired by
      re-running part of an old series — only by a brand-new full six in a fresh output directory.
