#!/usr/bin/env bash
# Show Lambda logs.
#
# Usage: scripts/logs.sh [api|ingest] [--tail]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

case "${1:-api}" in
  api) NAME=ApiFunction ;;
  ingest) NAME=IngestFunction ;;
  -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
  *) echo "Usage: $0 [api|ingest] [--tail]" >&2; exit 1 ;;
esac

TAIL=()
if [ "${2:-}" = "--tail" ]; then
  TAIL=(--tail)
fi

require_cmd sam
# The ${arr[@]+...} form keeps `set -u` happy on bash 3.x when empty.
sam logs --stack-name "$STACK_NAME" --region "$AWS_REGION" \
  --name "$NAME" ${TAIL[@]+"${TAIL[@]}"}
