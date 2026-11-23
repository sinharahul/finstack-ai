#!/usr/bin/env bash
# Shared config for the finstack-ai lifecycle scripts. Source this file;
# do not run it directly.
#
# Env overrides: STACK_NAME (default finstack-ai), AWS_REGION (default
# from AWS config, else us-east-1), AWS_PROFILE, AMPLIFY_REPO.
set -euo pipefail

_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$_COMMON_DIR/.." && pwd)"
SCRIPTS_DIR="$_COMMON_DIR"
TEMPLATE="$ROOT_DIR/infra/template.yaml"

STACK_NAME="${STACK_NAME:-finstack-ai}"
AWS_REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || echo us-east-1)}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: '$1' is not installed." >&2
    exit 1
  }
}

ensure_aws_login() {
  local arn
  if ! arn=$(aws sts get-caller-identity --query Arn --output text 2>&1); then
    echo "ERROR: AWS credentials are missing or invalid." >&2
    echo "$arn" >&2
    exit 1
  fi
  echo "AWS identity: $arn"
}

amplify_repo() {
  if [ -n "${AMPLIFY_REPO:-}" ]; then
    echo "$AMPLIFY_REPO"
    return 0
  fi
  git -C "$ROOT_DIR" remote get-url origin 2>/dev/null || {
    echo "ERROR: no git origin remote; set AMPLIFY_REPO." >&2
    return 1
  }
}
