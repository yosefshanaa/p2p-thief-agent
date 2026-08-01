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

## Deploy (any container platform)

```bash
# example shape - substitute your platform's CLI
<platform> deploy --image p2p-pursuit --env ROLE=police --env P2P_OPPONENT_URL=https://their-host/mcp
<platform> deploy --image p2p-pursuit --env ROLE=thief  --env P2P_OPPONENT_URL=https://their-host/mcp
```

Then exchange the two public URLs with the opposing team and run
`uv run p2p-pursuit smoke <their-url>` before agreeing anything else (RUNBOOK §3b).

## Honest status

| Piece | State |
|---|---|
| Peer binds `0.0.0.0` and honours `$PORT` | ✅ implemented + unit-tested |
| Opponent URL from the environment | ✅ implemented + unit-tested |
| Container image | ✅ provider-agnostic `Dockerfile`, role-parameterised |
| Six-sub-game series over the reference dialect | ✅ proven on localhost, every audit `Verified OK` |
| **Six-sub-game series over a real network path** | ⛔ **not yet proven.** The tunnel rehearsal was blocked by the 421 above. This is the last untested combination before a counted match. |
| A live public HTTPS URL | ⛔ external — needs your cloud account |

Nothing here fakes a deployment: the image and the env plumbing are verifiable locally today; the
live host and the public URL are the external step.
