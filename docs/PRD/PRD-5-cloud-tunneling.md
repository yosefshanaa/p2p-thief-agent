# PRD-5 — Stage 5: Cloud Exposure & Tunneling (book ch. 2 §2.4)

**Objective:** move from localhost to the public internet — expose each peer's FastMCP server via a
tunnel (ngrok / Localtonet), connect peers running on different machines, and survive real-network
latency and disconnects. From here the system is a genuine distributed system (#10).

## Scope
**In:** tunnel bring-up + docs, public-URL config wiring, NAT traversal validation, resilience
hardening under real latency, cross-machine run book, smoke checks, pre-game negotiation flow.
**Out:** crypto (next stage), league reporting (PRD-7).

## Functional requirements
1. **Tunnel runbook:** scripted/documented bring-up of ngrok (or Localtonet) exposing the local
   FastMCP port; the public URL is pasted into the *opponent's* private TOML (`opponent_url`).
   Document URL rotation (free-tier tunnels change per session) and re-negotiation on change.
2. **Environment separation:** unchanged code between localhost and tunnel — only config differs.
   Bind `0.0.0.0`, port from TOML.
3. **Resilience under WAN:** timeouts honored over high latency; deadline-tracker retries absorb
   transient tunnel hiccups; a fallen tunnel mid-game leads to the clean technical-loss path
   (book: tunnel robustness *is* game robustness). Reconnect-and-resume within the timeout window
   is attempted before declaring loss.
4. **Pre-game negotiation flow (`handshake` tool, now for real):** exchange team identity,
   proposed constitution, agree byte-identical `game.json` (minimums may only rise, #12),
   agree **first mover** (our proposal: thief) and any mutually agreed rule upgrades,
   exchange `config_sha256`, refuse to play on any mismatch (#11); persist the agreed per-match
   config copy under its unique name (goes to the repo). Guard: for a **counted** match,
   `num_games` must equal the binding 6 — reject the reference repo's demo default of 1.
5. **Smoke tool:** `smoke <url>` — health + round-trip latency + tool-contract probe against a
   remote peer (adapted from HW6's smoke pattern).

## Milestone (binary gate)
> An agent on a remote machine connects through ngrok and plays a full sub-game against the local
> agent; killing the tunnel mid-game yields a clean technical-loss (no hang, state persisted);
> a config mismatch is detected at handshake and the game refuses to start.

## Tests
Integration (semi-manual matrix): two machines × tunnel, latency injection, tunnel-kill drill,
handshake mismatch drill. Unit: negotiation state logic, config-copy naming.
