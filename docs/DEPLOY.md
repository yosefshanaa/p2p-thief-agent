# DEPLOY — putting both peers on stable public HTTPS

The alternative to tunnelling, and the better one for a counted match. A hosted peer has a URL
that does not rotate, HTTPS terminated by the platform, and — the part that actually matters —
**a server that is already running when the opponent starts theirs**.

## Why this beats a tunnel

Tunnels create a startup race that has nothing to do with the game. Measured on 2026-08-01:

| Symptom | Cause |
|---|---|
| `Opponent never sent its agreement` (their side), `opponent never came up` (ours) | A reference-derived peer allows ~60 s for our agreement, while each of our failed liveness probes costs its full 5 s timeout. Sixty attempts take minutes. **Fixed in code** — `wait_until_up` now returns the moment their agreement lands in our inbox, which is stronger evidence than any probe of ours. |
| `421 Misdirected Request` from `*.trycloudflare.com` | The Cloudflare edge rejected the request while the local origin answered `406` normally. Reproduced on a **fresh** tunnel, on both HTTP/1.1 and HTTP/2. Not a defect in this project — but not something you want between you and a graded match. |

Two always-on hosted servers have neither problem: nobody is waiting for anybody to boot.

## What the image needs

Nothing that can be committed. A container cannot know its own port or the opponent's address at
build time, so both come from the environment (`shared/config.apply_env_overrides`):

| Variable | Meaning |
|---|---|
| `PORT` | injected by Cloud Run / Render / Fly. The peer already binds `0.0.0.0`. |
| `P2P_MY_PORT` | explicit override; wins over `PORT` |
| `P2P_OPPONENT_URL` | the opponent's public `…/mcp` URL, exchanged out of band |
| `ROLE` | `police` or `thief` — deploy the image **twice**, once per role |
| `OPENAI_API_KEY` | only if `[trash_talk] provider = "openai"`; platform secret store, never the repo |

## Build and smoke-test locally

```bash
docker build -t p2p-pursuit .
docker run --rm -e ROLE=thief -e PORT=8081 -p 8081:8081 p2p-pursuit
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8081/mcp   # 406 = healthy MCP
```

`406` is the success case: a FastMCP endpoint refuses a bare `GET`. Configure the platform's
health check as a **TCP** probe, not HTTP, or it will read that 406 as a failure.

## Deploy — Google Cloud Run

The same platform HW6 went live on, and the account is already set up
(`gcloud auth list`, project `cop-thief-hw6-0f43`). Deploy **once per role**, two services:

```bash
gcloud run deploy p2p-pursuit-police --source . --region me-west1 --allow-unauthenticated \
  --min-instances=1 --max-instances=1 --no-cpu-throttling --timeout=3600 \
  --set-env-vars="ROLE=police,P2P_OPPONENT_URL=https://their-host/mcp" --quiet

gcloud run deploy p2p-pursuit-thief  --source . --region me-west1 --allow-unauthenticated \
  --min-instances=1 --max-instances=1 --no-cpu-throttling --timeout=3600 \
  --set-env-vars="ROLE=thief,P2P_OPPONENT_URL=https://their-host/mcp" --quiet
```

### Four flags that are not optional here

| Flag | Why this project needs it |
|---|---|
| `--min-instances=1 --max-instances=1` | The game state — belief map, commit chain, scent field — lives in memory. A second autoscaled instance forks the match; a cold start blows the opponent's ~60 s negotiate window. One instance, always warm. (HW6 learned this the same way.) |
| **`--no-cpu-throttling`** | New here. Cloud Run throttles CPU to near-zero between requests by default, and our peer drives its own turns from a background thread (`cli.py`, `name="series"`). Throttled, it stops playing the moment nobody is calling it — and forfeits on the turn timeout. |
| `--timeout=3600` | MCP streamable-HTTP sessions are long-lived; the 300 s default cuts them mid-series. |
| `--allow-unauthenticated` | Opens the network path. Unlike HW6 there is **no bearer token** in this project: the gate is the handshake's `config_sha256`, which refuses any peer not holding the byte-identical constitution. Strangers can reach the endpoint; they cannot start a game. |

### Two things a hosted peer cannot do by itself

Both are consequences of secrets and artifacts being git-ignored — correctly — and therefore
absent from the image:

1. **It cannot email the report.** `token.json` / `credentials.json` are not in the image, so the
   Gmail step will not run. A missing report forfeits that side's points (RUNBOOK §4). Neither
   file is something new to obtain: `credentials.json` is the OAuth client from the Cloud
   Console, and `token.json` is written by `uv run p2p-pursuit authorize`. Mount the pair you
   already have:

   ```bash
   gcloud secrets create p2p-gmail-token       --data-file=token.json
   gcloud secrets create p2p-gmail-credentials --data-file=credentials.json
   gcloud run services update p2p-pursuit-police --region me-west1 \
     --set-secrets="/app/token.json=p2p-gmail-token:latest,\
   /app/credentials.json=p2p-gmail-credentials:latest" --quiet
   ```

   A Secret Manager mount is **read-only** and the access token expires hourly, so
   `GmailTransport` persists a refresh best-effort rather than raising `Read-only file system`
   at exactly the moment the report is due. Re-uploading the secret after each `authorize` is
   the only maintenance: the OAuth app is in *testing* mode, where the refresh token lapses
   after ~7 idle days.
2. **Its artifacts are ephemeral.** `/app/results` dies with the instance, taking the sealed logs
   the `matches/` archive and any later `learn clone` depend on. Mount a GCS bucket at
   `/app/results` (`--add-volume` / `--add-volume-mount`) before a match that counts.

Neither matters for a **rehearsal**, which is what the outstanding WAN validation needs. Both
matter for a counted match.

Then exchange the two public URLs with the opposing team and run
`uv run p2p-pursuit smoke <their-url>` before agreeing anything else (RUNBOOK §3b).

## Honest status

| Piece | State |
|---|---|
| Peer binds `0.0.0.0` and honours `$PORT` | ✅ implemented + unit-tested |
| Opponent URL from the environment | ✅ implemented + unit-tested |
| Container image | ✅ provider-agnostic `Dockerfile`, role-parameterised |
| Six-sub-game series over the reference dialect | ✅ proven on localhost, every audit `Verified OK` |
| **Six-sub-game series over a real network path** | ✅ **proven 2026-08-01 on Cloud Run** — see below |
| A live public HTTPS URL | ✅ deployed (`me-west1`, project `cop-thief-hw6-0f43`) |

## Live result — Cloud Run, 2026-08-01

Both peers deployed as two services and cross-wired at each other's public URL. Several complete
six-sub-game series ran back to back, **every sub-game `audit=Verified OK`**. One of them:

| Sub-game | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Result | capture (barrier) | capture (**enclosed**) | capture (barrier) | capture (barrier) | capture (barrier) | capture (barrier) |

Three things this settles:

- **The protocol holds over a real network.** Commit-reveal, per-sub-game mutual audit, deadlines
  and the watchdog all survive genuine latency, TLS termination and a platform proxy. That was
  the last untested combination.
- **`$PORT` and `$P2P_OPPONENT_URL` work in production** — the hosted peer logged
  `FastMCP server on 0.0.0.0:8080` and `doctrine: tuned from /app/config/doctrine.json
  (20 of 20 fields differ from the defaults)`, so it played the tuned policy, not the fallback.
- **The barrier doctrine converts on the wire.** Almost every capture is `(barrier)` — the
  offline search's most counter-intuitive result (`belief_floor` 0.22 → 0.069, reversing v4's
  "barriers are a tempo trap") paying off in live matches rather than only in simulation.

It does **not** cover the reference dialect: both peers here are ours, so they speak native. The
reference-dialect series fixes are proven on localhost (RUNBOOK §3b), not yet over a network.

### Cost control

Both services are parked at `--min-instances=0`, so they cost nothing idle and the URLs survive.
**Before a counted match, put them back:**

```bash
gcloud run services update p2p-pursuit-police --region me-west1 --min-instances=1 --quiet
gcloud run services update p2p-pursuit-thief  --region me-west1 --min-instances=1 --quiet
```

At zero, the first inbound request cold-starts the container and begins a *fresh* series — fine
for sharing URLs ahead of a match, wrong for the match itself.

Nothing here fakes a deployment: the image, the env plumbing and the live series are all real.
