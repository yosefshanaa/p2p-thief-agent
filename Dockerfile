# One peer, provider-agnostic. Deploy it TWICE - once per role - so the two
# agents sit at two independent public URLs, exactly as a real match needs:
#
#   docker build -t p2p-pursuit .
#   docker run -e ROLE=police -e PORT=8080 -p 8080:8080 p2p-pursuit
#   docker run -e ROLE=thief  -e PORT=8081 -p 8081:8081 p2p-pursuit
#
# The platform injects $PORT and terminates HTTPS in front of the container;
# the peer already binds 0.0.0.0 and reads $PORT (shared/config.apply_env_overrides).
# Point it at the opponent with $P2P_OPPONENT_URL. See docs/DEPLOY.md.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    ROLE=police \
    PORT=8080 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so a code change does not re-resolve the world.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY config ./config
RUN uv sync --frozen --no-dev

EXPOSE 8080

# A TCP probe, not an MCP call: a healthy FastMCP endpoint answers 406 to a bare
# GET, which most platform HTTP probes read as failure.
HEALTHCHECK --interval=30s --timeout=3s --start-period=25s \
  CMD python -c "import os,socket; socket.create_connection(('127.0.0.1', int(os.environ['PORT'])), 2).close()"

# --no-gui is not optional here: there is no display in a container, and the
# live viewer is a local-truth debugging surface, never part of a served match.
CMD ["sh", "-c", "uv run p2p-pursuit peer --role ${ROLE} --no-gui --out /app/results"]
