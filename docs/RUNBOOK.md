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
