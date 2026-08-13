#!/usr/bin/env fish
# Launch a match in YOUR terminal, logs in front of you.
#
#   scripts/play.fish uoh-sqak https://their-tunnel.ngrok-free.app/mcp [--role police] [extra peer args]
#
# Loads the negotiated contract for that opponent from config/opponents/<name>.env,
# so the terms, dialect, scent model, doctrine and email mode are whatever was
# agreed with THEM - never edited into the committed constitution.

set -l opponent $argv[1]
set -l url $argv[2]
set -l rest $argv[3..-1]

if test -z "$opponent" -o -z "$url"
    echo "usage: scripts/play.fish <opponent-name> <their-/mcp-url> [peer args...]" >&2
    echo "       e.g. scripts/play.fish uoh-sqak https://xxxx.ngrok-free.app/mcp" >&2
    exit 2
end

set -l envfile config/opponents/$opponent.env
if not test -f $envfile
    echo "no contract file: $envfile" >&2
    exit 2
end

for line in (grep -vE '^#|^$' $envfile)
    set -x (string split -m1 = $line)
end
set -x P2P_OPPONENT_URL $url

# Default role is police unless the caller passes --role; keep it visible either way.
if not contains -- --role $rest
    set rest --role police $rest
end

# The sealed artifacts under results/ are the evidence that counts, but the
# terminal narrative is what explains a match afterwards - so keep both.
set -l stamp (date -u +%Y%m%dT%H%M%SZ)
mkdir -p logs
set -l transcript logs/$opponent-$stamp.log
echo "  transcript logs/$opponent-$stamp.log"

echo "=== contract: $opponent ==="
echo "  opponent   $P2P_OPPONENT_URL"
echo "  dialect    $P2P_DIALECT   alternate=$P2P_ALTERNATE_ROLES  rehandshake=$P2P_HANDSHAKE_PER_SUB_GAME"
echo "  scent      $P2P_SCENT_MODEL   doctrine=$P2P_DOCTRINE"
echo "  enclosure  $P2P_CLAIM_ENCLOSURE"
echo "  email      $P2P_EMAIL_MODE   <- 'draft' means a friendly CANNOT mail the lecturer"
echo "  args       $rest"
echo

uv run p2p-pursuit peer $rest 2>&1 | tee $transcript
