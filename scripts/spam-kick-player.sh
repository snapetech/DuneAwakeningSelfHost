#!/bin/sh
set -eu

usage() {
  cat >&2 <<'USAGE'
Usage: spam-kick-player.sh --player NAME [--fls-id ID] [--reason TEXT] [--message TEXT]

This is the hook shape expected by DUNE_CHAT_SPAM_KICK_COMMAND. It fails closed
until a verified targeted Dune kick backend is configured.
USAGE
}

PLAYER=""
FLS_ID=""
REASON=""
MESSAGE=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --player)
      PLAYER="${2:-}"
      shift 2
      ;;
    --fls-id)
      FLS_ID="${2:-}"
      shift 2
      ;;
    --reason)
      REASON="${2:-}"
      shift 2
      ;;
    --message)
      MESSAGE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [ -z "$PLAYER" ]; then
  echo "missing --player" >&2
  usage
  exit 2
fi

MODE="${DUNE_SPAM_KICK_BACKEND:-blocked}"

case "$MODE" in
  blocked|"")
    echo "targeted kick backend is not verified; refusing unsafe kick for player=$PLAYER fls_id=$FLS_ID reason=$REASON" >&2
    exit 70
    ;;
  command)
    if [ -z "${DUNE_SPAM_KICK_BACKEND_COMMAND:-}" ]; then
      echo "DUNE_SPAM_KICK_BACKEND_COMMAND is required when DUNE_SPAM_KICK_BACKEND=command" >&2
      exit 2
    fi
    # The backend command receives the same placeholder-capable argv shape.
    set -- ${DUNE_SPAM_KICK_BACKEND_COMMAND} --player "$PLAYER" --fls-id "$FLS_ID" --reason "$REASON" --message "$MESSAGE"
    exec "$@"
    ;;
  *)
    echo "unknown DUNE_SPAM_KICK_BACKEND=$MODE" >&2
    exit 2
    ;;
esac
