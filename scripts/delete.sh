#!/usr/bin/env bash
# Delete the entire stack and all its data.
#
# Usage: scripts/delete.sh --yes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

if [ "${1:-}" != "--yes" ]; then
  echo "This deletes stack '$STACK_NAME' ($AWS_REGION) and ALL its data." >&2
  echo "Rerun with --yes to confirm." >&2
  exit 1
fi

require_cmd sam
require_cmd aws
ensure_aws_login

sam delete --stack-name "$STACK_NAME" --region "$AWS_REGION" --no-prompts
echo "Note: the SAM-managed S3 deployment bucket is left behind by design"
echo "(negligible cost); delete it manually if you want it gone."
