#!/usr/bin/env bash
# Show stack status, outputs, search-tier state, and API health.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_cmd aws

echo "== Stack $STACK_NAME ($AWS_REGION) =="
STATUS="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" --query 'Stacks[0].StackStatus' --output text 2>&1)" || {
  echo "Stack '$STACK_NAME' not found in $AWS_REGION."
  exit 1
}
echo "Status: $STATUS"
aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" --query 'Stacks[0].Outputs' --output table

echo "== Search tier =="
aws opensearchserverless batch-get-collection --names finstack-filings \
  --region "$AWS_REGION" \
  --query 'collectionDetails[0].{name:name,status:status}' \
  --output table 2>/dev/null \
  || echo "(collection absent — run start.sh to enable search)"
COLL_ENDPOINT="$(aws opensearchserverless batch-get-collection \
  --names finstack-filings --region "$AWS_REGION" \
  --query 'collectionDetails[0].collectionEndpoint' \
  --output text 2>/dev/null || echo none)"
if [ "$COLL_ENDPOINT" != "none" ] && [ "$COLL_ENDPOINT" != "None" ]; then
  echo "Endpoint: $COLL_ENDPOINT"
fi

if command -v curl >/dev/null 2>&1; then
  ENDPOINT="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --region "$AWS_REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text)"
  if [ -n "$ENDPOINT" ] && [ "$ENDPOINT" != "None" ]; then
    CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
      "$ENDPOINT/health" || echo "unreachable")"
    echo "GET /health -> $CODE"
  fi
fi
