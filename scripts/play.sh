#!/usr/bin/env bash
# Launch a match from bash or zsh - the portable twin of scripts/play.fish.
#
#   scripts/play.sh <opponent> <their-/mcp-url> [peer args...]
#   scripts/play.sh newteam https://xxxx.trycloudflare.com/mcp --role police
#   scripts/play.sh newteam https://xxxx.trycloudflare.com/mcp --counted --prior-counted 2
#
# Exists because play.fish needs fish, and `uv run` is not usable on every
# machine in this team (an iCloud-synced checkout re-hides the venv's .pth
# files, so `uv run` breaks the next command you type). This script needs
# neither: it finds a working runner itself and always sets PYTHONPATH=src.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)

opponent=${1:-}
url=${2:-}
if [ -z "$opponent" ] || [ -z "$url" ]; then
    echo "usage: scripts/play.sh <opponent-name> <their-/mcp-url> [peer args...]" >&2
    echo "       contracts available:" >&2
    ls config/opponents/*.env 2>/dev/null | sed 's|.*/|         |; s|\.env$||' >&2
    exit 2
fi
shift 2
rest=("$@")

envfile="config/opponents/${opponent}.env"
if [ ! -f "$envfile" ]; then
    echo "no contract file: $envfile" >&2
    echo "copy config/opponents/TEMPLATE.env and fill in what they told you." >&2
    exit 2
fi

# The contract, exactly as the .env files document it.
set -a
# shellcheck disable=SC1090
. "$envfile"
set +a
export P2P_OPPONENT_URL="$url"

# -- find a runner ------------------------------------------------------------
# uv first, but only if it can actually import the package; a checkout whose
# .pth files have been hidden passes `which uv` and then fails on import.
RUNNER=""
if command -v uv >/dev/null 2>&1 && uv run python -c "import p2p_pursuit" >/dev/null 2>&1; then
    RUNNER="uv run p2p-pursuit"
elif [ -x "$ROOT/.venv/bin/p2p-pursuit" ]; then
    export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
    RUNNER="$ROOT/.venv/bin/p2p-pursuit"
elif [ -x "$ROOT/.venv/bin/python" ]; then
    export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
    RUNNER="$ROOT/.venv/bin/python -m p2p_pursuit"
else
    echo "no runner: neither a working 'uv run' nor .venv/bin/p2p-pursuit" >&2
    exit 2
fi

# -- default role, kept visible ----------------------------------------------
case " ${rest[*]-} " in
    *" --role "*) ;;
    *) rest=(--role police "${rest[@]-}") ;;
esac

# -- counted or friendly, said out loud --------------------------------------
LECTURER="rmisegal+uoh26finalgame@gmail.com"
counted="no"
case " ${rest[*]-} " in *" --counted "*) counted="yes" ;; esac

recipient="${P2P_EMAIL_RECIPIENT:-<committed default: $LECTURER>}"
mode="${P2P_EMAIL_MODE:-<committed default>}"

echo "=== contract: $opponent ==="
echo "  opponent    $P2P_OPPONENT_URL"
echo "  runner      $RUNNER"
echo "  dialect     ${P2P_DIALECT:-native}   alternate=${P2P_ALTERNATE_ROLES:-false}  rehandshake=${P2P_HANDSHAKE_PER_SUB_GAME:-false}"
echo "  scent       ${P2P_SCENT_MODEL:-book_v1}   doctrine=${P2P_DOCTRINE:-<default>}"
echo "  game_id     ${P2P_GAME_ID:-<derived>}"
echo "  COUNTED     $counted"
echo "  email       mode=$mode -> $recipient"
echo "  args        ${rest[*]-}"
echo

# The one mistake that cannot be undone: a friendly filed against the lecturer
# reads as THE counted encounter, and the book allows exactly one per pair.
if [ "$counted" = "no" ] && [ "$mode" = "send" ] && \
   { [ "${P2P_EMAIL_RECIPIENT:-}" = "$LECTURER" ] || [ -z "${P2P_EMAIL_RECIPIENT:-}" ]; }; then
    echo "REFUSING: this is a FRIENDLY (no --counted) but the report would be SENT" >&2
    echo "          to the lecturer. Set P2P_EMAIL_MODE=draft, or point" >&2
    echo "          P2P_EMAIL_RECIPIENT at your own address, then re-run." >&2
    exit 3
fi
if [ "$counted" = "yes" ]; then
    echo "*** COUNTED MATCH. One per pair, sealed once both reports are filed."
    echo "*** Report goes to: $recipient"
    printf '*** Type EXACTLY "counted" to proceed: '
    read -r confirm
    [ "$confirm" = "counted" ] || { echo "aborted." >&2; exit 4; }
    echo
fi

mkdir -p logs
stamp=$(date -u +%Y%m%dT%H%M%SZ)
transcript="logs/${opponent}-${stamp}.log"
echo "  transcript  $transcript"
echo

# shellcheck disable=SC2086
$RUNNER peer "${rest[@]-}" 2>&1 | tee "$transcript"
