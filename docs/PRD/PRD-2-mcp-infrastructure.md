# PRD-2 — Stage 2: FastMCP P2P Infrastructure (book ch. 2 + 8)

**Objective:** split the two agents into fully separate processes, each a **FastMCP server +
client** on localhost, exchanging *purely geometric* payloads — prove the pipe before loading it
with scent, language, or crypto.

## Scope
**In:** PeerRuntime skeleton, MCP server (tools) + client (transport), Orchestrator gateway,
state machine, deadline tracker, watchdog, structured logging skeleton, process/config separation.
**Out:** public tunneling (PRD-5), commit-reveal payload content (PRD-6 — but envelope fields are
reserved now), scent/hints (PRD-4).

## Functional requirements
1. **Two processes** (`--role police` / `--role thief`), separate config dirs `/config/police` vs
   `/config/thief`; zero shared runtime state — no module holds live state importable by both (#1–2).
2. **MCP server per peer** (FastMCP, `transport="http"`, own port; dev convention thief 8801,
   police 8802). Tools (contract frozen here, payloads enriched by later stages):
   `handshake` (identity, config_sha256, negotiation), `receive_commit`, `acknowledge`,
   `receive_reveal`, `capture_claim`, `audit_exchange` (nonce dump), `game_status`, `health`.
3. **MCP client**: connects to `opponent_url` from private TOML; **retry-until-up** at start
   (start order must not matter); every call stamped with timestamp + deadline.
4. **Orchestrator gateway** (#3): sole entry point wiring MCP connector, decision module (stub),
   log manager, deadline tracker, watchdog; no peripheral module talks to another directly.
5. **State machine** (#4–5): states `WAITING_FOR_OPPONENT, COMPUTING_MOVE, COMMITTING,
   AWAITING_REVEAL, VERIFYING, TECHNICAL_LOSS(terminal)`; transition table enforced; illegal
   transition ⇒ immediate exception (dev) / technical-loss path (play).
6. **Deadline Tracker** (#6): per-request expiry (`response_timeout_sec`, default 30 s), bounded
   retries, then declare technical loss cleanly — a request never waits unbounded. Distinct from
   the **turn timeout** (`turn_timeout_seconds`, private TOML, default 180 s): the maximum total
   wait for the opponent's turn before declaring a technical loss.
   First mover is not fixed by the book — it is a `handshake` negotiation field (our default
   proposal: thief first).
7. **Watchdog** (#7): background heartbeat monitor (`[watchdog threshold]`, default 60 s);
   on freeze: persist state, controlled shutdown (close MCP + logs), exit code distinct from crash.
8. **Log manager:** every step appended as one JSON record (schema gains crypto fields in PRD-6)
   to `logs/<group>/log_<game_id>_g<NN>.json`.

## Milestone (binary gate)
> A geometric message leaves peer A and is received and parsed correctly by peer B over localhost;
> start order irrelevant; killing B mid-wait drives A through `TECHNICAL_LOSS` (no hang);
> freezing A's main loop triggers the watchdog's controlled shutdown with persisted state.

## Tests
Unit: transition table (all legal + representative illegal), deadline expiry/retry, watchdog
threshold, tool schemas. Integration: two subprocesses complete N scripted turns; chaos tests
(kill/freeze/latency injection).
