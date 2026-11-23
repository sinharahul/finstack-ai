#!/usr/bin/env bash
# Start the search tier (OpenSearch collection) via a stack update.
# Creates the stack if it does not exist yet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/deploy.sh" --search
