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
if [ -z "$opponent" ]; then
    echo "usage: scripts/play.sh <opponent-name> [their-/mcp-url] [peer args...]" >&2
    echo "       the URL is optional when the contract names both doors itself" >&2
    echo "       contracts available:" >&2
    ls config/opponents/*.env 2>/dev/null | sed 's|.*/|         |; s|\.env$||' >&2
    exit 2
fi
shift

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

# The URL is positional ONLY when it is really the next argument - a peer arg
# like `--role` never is. A contract that names a door per role (a peer running
# one process per role on two ports, which `{role}` cannot express) carries its
# own addresses and needs no positional at all; demanding one there invites
# pasting a single door and then wondering why half the sub-games dial it.
url=""
case "${1:-}" in
    -*|"") ;;
    *) url=$1; shift ;;
esac
if [ -n "$url" ]; then
    export P2P_OPPONENT_URL="$url"
elif [ -z "${P2P_OPPONENT_COP_URL:-}${P2P_OPPONENT_THIEF_URL:-}${P2P_OPPONENT_URL:-}" ]; then
    echo "no opponent address: pass their /mcp URL, or set P2P_OPPONENT_COP_URL /" >&2
    echo "P2P_OPPONENT_THIEF_URL in $envfile" >&2
    exit 2
fi
rest=("$@")

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

# -- headless by default ------------------------------------------------------
# cli.py plays the series on a worker thread and mails the report only after
# LiveView.run() returns (cli.py:52-58). An open GUI therefore holds a finished
# report hostage indefinitely - measured 2026-08-16, a completed friendly sat
# unsent behind a window nobody knew to close. `--gui` opts the window back in
# and is consumed here rather than forwarded, since the CLI has no such flag.
want_gui="no"
filtered=()
for a in ${rest[@]+"${rest[@]}"}; do
    if [ "$a" = "--gui" ]; then want_gui="yes"; else filtered+=("$a"); fi
done
rest=(${filtered[@]+"${filtered[@]}"})
if [ "$want_gui" = "no" ]; then
    case " ${rest[*]-} " in *" --no-gui "*) ;; *) rest+=(--no-gui) ;; esac
fi

# Resolve what would ACTUALLY be sent by asking the loader that decides it,
# rather than reading the env vars and guessing at the committed defaults.
# Reading the vars alone leaves the likeliest mistake uncaught: a contract
# copied from TEMPLATE.env that simply omits P2P_EMAIL_MODE resolves here to
# the literal string "<committed default>", which is not "send", so the guard
# below would wave through a friendly bound for the lecturer. The TOML default
# is mode=send to the lecturer, so absence is the dangerous case, not the safe
# one. Verified 2026-08-16: env-only checks pass that contract.
role="police"
prev=""
for a in ${rest[@]+"${rest[@]}"}; do
    [ "$prev" = "--role" ] && role="$a"
    prev="$a"
done
config_dir="config/$role"
prev=""
for a in ${rest[@]+"${rest[@]}"}; do
    [ "$prev" = "--config-dir" ] && config_dir="$a"
    prev="$a"
done
eff=$("$ROOT/.venv/bin/python" - "$config_dir" <<'PY'
import sys
from pathlib import Path
from p2p_pursuit.shared.config import load_role
_, peer = load_role(Path(sys.argv[1]))
print(peer.email_mode)
print(peer.email_recipient)
PY
) || eff=""
mode="$(printf '%s\n' "$eff" | sed -n 1p)"
recipient="$(printf '%s\n' "$eff" | sed -n 2p)"
[ -n "$mode" ] || { echo "cannot resolve the email mode - refusing to guess" >&2; exit 2; }

echo "=== contract: $opponent ==="
# Under `set -u` a bare $P2P_OPPONENT_URL is fatal for a door-per-role
# contract, which sets no single URL at all - and the banner is the last
# thing that runs before the peer starts, so it took the launch with it.
if [ -n "${P2P_OPPONENT_COP_URL:-}${P2P_OPPONENT_THIEF_URL:-}" ]; then
    echo "  opponent    cop=${P2P_OPPONENT_COP_URL:-<none>}"
    echo "              thief=${P2P_OPPONENT_THIEF_URL:-<none>}"
else
    echo "  opponent    ${P2P_OPPONENT_URL:-<none>}"
fi
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
if [ "$counted" = "no" ] && [ "$mode" = "send" ] && [ "$recipient" = "$LECTURER" ]; then
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

# -- did the report actually leave? -------------------------------------------
# A played series and a delivered report are two different things, and the gap
# between them is silent - the sealed files land under results/ either way.
# Worse, when Gmail is unreachable `pick_email_transport` substitutes a dry-run
# transport that returns `delivered: True` with receipt id "dry-run-N", which
# reads as success and sends nothing. So check for that explicitly.
echo
if grep -q "\[email\].*'delivered': True" "$transcript" && \
   ! grep -q "\[email\].*dry-run" "$transcript"; then
    echo "email: DELIVERED - $(grep -o "\[email\].*" "$transcript" | tail -1)"
elif grep -q "\[email\].*dry-run" "$transcript"; then
    echo "email: NOT SENT - the dry-run transport stood in for Gmail." >&2
    echo "  'delivered: True' above is that dry run reporting itself." >&2
    echo "  check credentials.json/token.json, then resend with scripts/send_report.py" >&2
elif grep -q "\[email\]" "$transcript"; then
    echo "email: NOT DELIVERED - $(grep -o "\[email\].*" "$transcript" | tail -1)" >&2
else
    latest=$(ls -td results/*/ 2>/dev/null | head -1)
    echo "email: NEVER ATTEMPTED - the run ended before cli.py's report step." >&2
    if [ -n "$latest" ]; then
        res=$(ls "$latest"result_*.json 2>/dev/null | head -1)
        [ -n "$res" ] && {
            echo "  the match itself is filed under $latest" >&2
            echo "  send it with: scripts/send_report.py $res --to <address>" >&2
        }
    fi
fi
