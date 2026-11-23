#!/usr/bin/env bash
# Stop the search tier: removes the OpenSearch collection (the only
# idle-cost resource) while keeping the API, tables, bucket, and app.
# Re-run start.sh to bring it back.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/deploy.sh" --no-search
