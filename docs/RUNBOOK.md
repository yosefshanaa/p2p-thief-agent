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

## 3b. Interop with reference-derived opponents

The lecturer's example repo exposes a different tool surface — `negotiate`, `receive_turn`
(one message per turn), `submit_audit`, `receive_control` — while ours mirrors the book's
four-phase figure: `handshake`, `receive_commit` → `receive_reveal` → `receive_event`,
`audit_exchange` (+ `get_status`, `health_check`). The *cryptographic content* is identical
(commit = SHA-256 of the sealed record, nonce withheld until the audit — confirmed in the
reference's `protocol.py`), so this is a naming/framing difference only. The wire contract is
pair-negotiated (book: the constitution is set "in negotiation between each pair of teams"):
agree during warm-ups which surface the match uses; adapting is a thin transport-level shim on
either side (`infra/mcp_client.py` isolates every outbound call; the service facade isolates
every inbound one). Do this in an **uncounted warm-up first** — never discover a contract
mismatch inside a counted match.

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
