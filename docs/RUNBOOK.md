# RUNBOOK — Tunneling & League Match Operations

How to take a peer from localhost to the public internet and run a real match (PRD-5).

## 1. Expose your peer (ngrok)

```bash
# terminal A - your peer's FastMCP server (thief 8801 / police 8802):
uv run p2p-pursuit peer --role thief          # binds 0.0.0.0:8801

# terminal B - the tunnel:
ngrok http 8801            # note the https://xxxx.ngrok-free.app URL
```

Give the opponent `https://xxxx.ngrok-free.app/mcp`. Localtonet works the same way
(`localtonet http 8801`). **Free-tier URLs rotate on every tunnel restart** — if the tunnel
drops mid-series, restart it, send the opponent the new URL, and re-handshake; a peer that
stays silent past `turn_timeout_seconds` (180 s) forfeits that sub-game as a technical loss.

## 2. Wire the opponent

In `config/<role>/game.toml`:

```toml
[network]
opponent_url = "https://their-tunnel.ngrok-free.app/mcp"
```

Verify before playing:

```bash
uv run p2p-pursuit smoke https://their-tunnel.ngrok-free.app/mcp
```

## 3. Pre-match negotiation (both teams)

1. Agree every `game.json` value (minimums may only rise). Both sides must load a
   **byte-identical** file — the handshake exchanges `config_sha256` and refuses on mismatch.
2. Exchange the scent-model lock (formula + 0.9→0.81 example — `scent_model_document()`);
   sharing our `domain/scent.py` with the opponent is allowed and recommended (book rule #23).
3. Agree the first mover (our default proposal: thief).
4. Declare truthfully how many counted games each team has already played (#37).
5. For a **counted** match run with `--counted` — it refuses to start unless `num_games` is 6.

```bash
uv run p2p-pursuit peer --role thief --counted --prior-counted 1
```

## 3b. Interop with reference-derived opponents — built and proven

**Run this first against any new opponent:**

```bash
uv run p2p-pursuit smoke <their-url>     # prints dialect=native|reference|unknown
```

The probe lists the opponent's MCP tools and names the dialect, so the wire contract is a
warm-up fact instead of a mid-match surprise. (Liveness comes from the tool listing, not from
our `health_check`: a reference peer does not serve one and would otherwise read as dead.)

To play a reference-derived peer, set **one** switch in `config/<role>/game.toml`:

```toml
[interop]
dialect = "reference"     # native (default) | reference
```

That turns on the whole adaptation: their tool names inbound *and* outbound, their message
framing, and their commit formula.

### The four differences that actually matter

An earlier draft of this runbook claimed the cryptographic content was "identical" and only the
names differed. **That was wrong**, and reading their source proved it:

| # | Difference | Consequence |
|---|---|---|
| 1 | **Tool surface** — `negotiate` / `receive_turn` / `submit_audit` / `receive_control` vs our four-phase set | naming only; adapted in `infra/interop_codec.py` |
| 2 | **Framing** — every tool of theirs returns `{"ok": true}` and the *reply arrives as a separate push* into our server; ours is request/response | needs an inbox, not a rename — `infra/interop_bridge.py` |
| 3 | **Commit formula** — ours hashes the record with the nonce *inside* it; theirs hashes `canonical(payload)\|nonce` | **neither side can verify the other at all** until one adopts the other's digest |
| 4 | **Sealing coverage** — their `claim_response` and `win_claim` ride as *plain unsealed fields*; ours are cryptographically bound (rule #21) | we act on them but record them as unsealed (`peer/unsealed_events.py`) |

Difference 3 is the one that decides whether a match can produce a mutual `Verified OK`. Their
`audit_records` re-verifies hash binding only — it does not re-derive legality from their record
shape — so sealing our own records with **their** digest and revealing them in their
`{payload, nonce, commit}` envelope is enough for an *unmodified* reference peer to verify us.
`[interop] dialect = "reference"` does exactly that; `commit_dialect` is written into every log
so replays stay verifiable afterwards.

### Warm-up result — executed 2026-07-29 (uncounted)

Our peer (police) played a full 35-step sub-game against an **unmodified** reference peer
(thief, `--stub-llm`) on localhost. Both sides completed and **agreed the outcome**:

| Side | Verdict | Score |
|---|---|---|
| Reference peer's audit of **our** log | `log_verified: true`, `tampered: false` | thief 10 |
| Our audit of **their** log | `Verified OK` | police 5 |

Two real defects surfaced, both now fixed and covered by
`tests/integration/test_interop_bridge.py`:

1. **Their reporting crashed after a completed game** because our identity payload omitted
   `mcp_servers` / `llm_model` / `spec`, which their `group_block` indexes directly. A warm-up
   that "played fine" would still have produced no report from them.
2. **Our replay viewer stamped a clean interop match `TAMPERED`** — it re-hashed their
   `{payload, nonce, commit}` envelopes as if they were our sealed records. It now verifies
   their envelope on their terms and renders both sides' moves.

### ⚠️ A one-sub-game warm-up hides two series-level mismatches

The warm-up above played **one** sub-game — and that is precisely the configuration in which two
match-voiding differences are invisible. Running the same pairing with `--games 2` reproduces
both (2026-07-30):

1. **They re-negotiate before every sub-game; we handshake once per series.** Their series
   rebuilds a fresh `PeerRuntime` per sub-game and calls `negotiate` again. Our peer completes
   one handshake at connect time and never sends a second agreement, so their peer dies at
   sub-game 2 with `Opponent never sent its agreement`, while ours waits out its turn timeout.
   **Observed:** sub-game 1 finished normally (`survival`, audit `Verified OK`); sub-game 2
   produced no outcome at all.
2. **They alternate roles across sub-games; we hold one role for the series.** Their
   `sdk/series.py` `role_for()` plays the config-natural role on odd sub-games and the opposite
   on even ones. Our `--role` is fixed for the whole run, so from sub-game 2 both peers would
   claim the same role (our bridge's role-collision guard turns that into a technical loss).

A counted match is **six** sub-games, so either difference alone voids it. The book does not
settle this — the sub-game count is a template placeholder in the spec and role alternation is
not specified — which makes it exactly the kind of pair-negotiated constitution item that must
be agreed explicitly, like the wire dialect.

**Both are now supported**, off by default (our published repos are role-fixed), in
`config/<role>/game.toml`:

```toml
[interop]
dialect = "reference"
alternate_roles = true          # natural role on odd sub-games, opposite on even
handshake_per_sub_game = true   # re-negotiate before every sub-game
```

Verified live on 2026-07-30 against the unmodified reference peer with `--games 2`: sub-game 1
played us as police (their thief survived 35), sub-game 2 logged
`playing as thief (alternating)` and ran to a capture. Both sub-games completed — the same
pairing died at sub-game 2 before this.

**Warm up with `--games 2` at minimum, never `--games 1`.** Sub-game 2 is where series-level
assumptions first surface. And settle two questions with every opponent: *do we re-handshake
per sub-game, and do roles alternate?*

### What interop still cannot give you

Our audit of a reference peer checks hash binding, that **every commitment we witnessed live is
actually revealed** (their own audit does not check this), and trajectory continuity. It does
**not** re-derive scent honesty or barrier quota from their record shape, and their protocol
never exchanges a scent-model lock, so rule #23 cannot be mutually enforced in this dialect.
Their peer also keeps its verdict of us to itself, so `mutual_agreement` in our result is
`false` for an interop match — truthfully, since we never received their verdict.

**Therefore: prefer the native dialect for counted matches** when the opponent will run our
shim, and use reference dialect when they will not. Either way, warm up uncounted first.

## 3c. How the league actually scores you (book §9.2.1 + §9.2.2, pp. 86–87)

Read before scheduling, because it changes match-day choices:

- **One counted game per opponent, full stop.** Once both teams agree the result and send their
  reports, "the encounter with that opponent is sealed" — you may not replay them for points.
  So each counted match is a single, unrepeatable shot: warm up first, every time.
- **Warm-ups are explicitly encouraged** and do not count. There is no downside to running two
  or three against the same team before the counted one.
- **The diversity incentive rewards a *victory* over an opponent you have not played** — not
  merely playing them. A tie earns the tie score, not the bonus. More distinct opponents means
  more chances at the bonus, capped at the per-team maximum.
- **Declare your counted-game count truthfully at the start of every match.** The weighting is
  computed from the mutual declarations, and the lecturer independently receives both teams'
  reports — so a false declaration is detectable and disqualifies the team that made it.
- **Computational fairness cuts the score advantage of heavy compute** and rewards efficient
  algorithms on modest machines: the book's words are that the league rewards "wisdom in
  development, not raw compute".
- **But the LLM is expected to be used, judiciously.** The lecturer's own guidance is that the
  game "was designed so it can be played without any LLM at all — obviously the hope is that you
  make *judicious* use of the LLM". So the answer is neither zero tokens nor a call every step:
  run counted matches with `provider = "openai"` and **`every_n_steps = 3`**, which keeps the
  banter genuinely LLM-authored while cutting ~420 calls per series to ~140 (about ten minutes
  and two-thirds of the tokens saved) with no strategic loss — moves are pure Python regardless
  (rule #25). That is the defensible reading of both constraints at once.

Practical consequence: since capture is hard (STRATEGY.md §6) and an all-survival series ties
45–45 under role alternation, the points come from (a) never losing a sub-game — our thief is
uncaptured in every external match to date — (b) never taking a technical loss, which is what
the protocol hardening protects, and (c) beating the weaker half of the field, where our police
converts at ~40% against a competent-but-not-perfect evader.

## 4. After the match

Each side automatically: audits the opponent's sealed log, writes the four artifacts under
`results/<role>-<game_id>/`, and emails `result_<game_id>.json` to
`rmisegal+uoh26finalgame@gmail.com` (**both teams send separately** — a missing report forfeits
that side's points).

**Archive the match** (Appendix F requires per-match configs in the repo; `results/` is
git-ignored, `matches/` is tracked):

```bash
cp -r results/<role>-<game_id> matches/ && git add matches && git commit -m "match: <game_id>"
```

Evidence kit per match: live-GUI belief-heatmap screenshot, replay `Verified OK` screenshot
(`uv run p2p-pursuit replay --log results/.../log_*_g01.json`), terminal output, Gmail id.

### 4b. Learn from the match you just played — do this before the next one

The sealed logs you just archived contain the opponent's **exact position and move at every
step**: a finished match is a few hundred labelled decisions by a real team, which is the one
thing a simulator built out of our own brains cannot invent. Turn it into a sparring partner and
re-tune against a pool that now includes them:

```bash
uv run p2p-pursuit learn clone --match matches/<archived-dir> --name <team>
uv run p2p-pursuit learn tune  --role police --generations 20 --seeds 40 --workers 12
uv run p2p-pursuit learn tune  --role thief  --generations 20 --seeds 40 --workers 12
uv run ruff check && uv run pytest --cov          # the doctrine is code; it ships like code
git add config/doctrine.json config/opponents && git commit -m "learn: after <team>"
```

Three rules, none of them optional:

1. **Never tune during a match.** A counted match plays the committed
   `config/doctrine.json` and nothing else. The report pins each sub-game to a `github_commit`;
   a peer that retunes itself between sub-games cannot be reproduced from that hash, and the
   version that won sub-game 2 would not be the version that played sub-game 5.
2. **The hold-out decides, and `tune` enforces it.** It writes the file only when a seed set
   the search never saw improves. A gain on the training seeds is the optimizer reporting its own
   noise. `--force` exists for experiments and has no place before a counted match.
3. **Re-run the suite after writing the file.** `config/doctrine.json` changes how both brains
   play; the v4/v5 doctrine regressions in `tests/unit/test_brains_v4.py` are what catch a tuned
   vector that has quietly re-created a defect the doctrine already paid to fix.

Cloning is honest by construction — the logs were mutually revealed by the protocol's own audit
exchange, after the match was over — but state its limit when you write it up: the fitted policy
uses *our* position, not their estimate of it, so it captures a team's revealed **style**
(straight-line flight, centre-holding, wall-hugging, barrier-spending) and not their inference.

## 5. Gmail OAuth (one-time)

```bash
uv run p2p-pursuit authorize     # opens browser consent; writes token.json (send-only scope)
```

`credentials.json` (client id/secret — reused from HW6) and `token.json` are git-ignored.
Testing-mode refresh tokens expire after ~7 days of disuse — rerun `authorize` if sends start
failing with `invalid_grant`. Set `[email] mode = "send"` for league matches (`draft` = local
dry-run; the send-only scope cannot create real Gmail drafts).

## 6. Live tunnel drill — executed 2026-07-29 (GATE M5 evidence)

Both peers were cross-wired through **two** public HTTPS tunnels (one per role) so traffic in
*both* directions left the machine. Confirmation that it was genuinely remote: each peer logged
its inbound requests from the public IP `89.138.5.166`, never `127.0.0.1`.

| Drill | Result |
|---|---|
| Full sub-game across the internet | completed; **both peers independently reported `audit=Verified OK`** |
| Tunnel killed mid-match | `ending=technical_loss`, totals **0/0**, `watchdog_state.json` written, both processes exited — **no hang** |

### Two operational lessons

1. **Start both peers within the connect window.** Each peer retries its opponent for a bounded
   time and then exits with `opponent never came up`. Bringing one up minutes before the other
   guarantees a failed match — open the tunnels first, exchange URLs, then start together.
2. **A dead link cascades, and that is correct.** Killing one tunnel made the first peer exit;
   its origin then disappeared, so the *other* tunnel began returning 502 and the second peer
   also declared a technical loss. Both sides independently recorded 0/0, which is the book's
   intended outcome — but note the peer that dies inside a sub-game handshake exits **without
   emitting a result report**. The match is void either way, yet rule #35 expects both teams to
   report; if a counted match ever dies this way, send the result manually from the artifacts.

### Bug found by this drill — watchdog vs. turn timeout (fixed)

The drill exposed a defect that **only appears over a real network**. The agreed turn timeout is
**180 s**, but the watchdog threshold is **60 s**, and the peer spent the whole turn wait inside
one blocking `wait_for_my_turn` call without emitting a heartbeat. Over localhost an opponent
always answers within 60 s, so it never fired; over a tunnel the watchdog decided our own
healthy peer had frozen, persisted state and shut it down — a **self-inflicted technical loss
in the middle of a working match**. The retry path had the same shape: a full budget
(4 attempts × 30 s + backoff) also outlasts the watchdog.

Fixed by slicing the wait and beating between slices, and by beating on every deadline attempt.
The watchdog keeps its purpose — a genuinely frozen loop never reaches that code, so it still
stops beating and is still caught. Re-running the same match afterwards produced **zero**
watchdog firings where the previous run had killed the peer.

### ngrok (spec default) vs the no-account fallback

`opponent_url` is just a public URL, so any tunnel works and the code path is identical. ngrok
is installed but needs a one-time credential:

```bash
ngrok config add-authtoken <token-from-dashboard.ngrok.com>
ngrok http 8801                        # thief;  use 8802 for police
```

A Cloudflare quick tunnel (`cloudflared tunnel --url http://localhost:8801`) needs no account
and was used for the drill above when ngrok's credential was not yet available.

### Tunnel choice for counted matches — measured

| Tunnel | Handshake | Full sub-game with mutual audit |
|---|---|---|
| Cloudflare quick tunnel | ✅ | ✅ `Verified OK` on both sides |
| ngrok free tier | ✅ 200 OK | ⚠️ MCP session dropped mid-game (`Client failed to connect`) with the agent healthy and the peer still serving |

ngrok authenticates and proxies fine, but the free tier did not hold the long-lived
streamable-HTTP MCP session for a whole sub-game. **Recommendation: run counted matches over a
Cloudflare quick tunnel (or Localtonet, also permitted by the book), and treat ngrok free as a
handshake-capable fallback.** This is a hosting-tier characteristic, not a defect in the peer —
the identical peer build completes cleanly over Cloudflare.
