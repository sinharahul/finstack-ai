#!/usr/bin/env bash
# Build and deploy the finstack-ai stack.
#
# Usage: scripts/deploy.sh [--search|--no-search]
# Env: STACK_NAME, AWS_REGION, AWS_PROFILE, AMPLIFY_REPO (see common.sh).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

ENABLE_SEARCH="${ENABLE_SEARCH:-true}"
for arg in "$@"; do
  case "$arg" in
    --search) ENABLE_SEARCH=true ;;
    --no-search) ENABLE_SEARCH=false ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $arg" >&2; exit 1 ;;
  esac
done

require_cmd sam
require_cmd aws
ensure_aws_login

REPO="$(amplify_repo)"
REPO="${REPO%.git}"
OVERRIDES=("AmplifyRepo=$REPO" "EnableSearch=$ENABLE_SEARCH")
if [ -n "${AMPLIFY_GITHUB_TOKEN:-}" ]; then
  OVERRIDES+=("GitHubToken=$AMPLIFY_GITHUB_TOKEN")
else
  echo "(no AMPLIFY_GITHUB_TOKEN: Amplify app will be created unconnected;"
  echo " link the repo in the Amplify console, or re-run with the token set)"
fi
echo "Stack:   $STACK_NAME ($AWS_REGION)"
echo "Search:  $ENABLE_SEARCH"
echo "Amplify: $REPO"

cd "$ROOT_DIR"
sam build --template-file "$TEMPLATE"

echo "Installing Lambda dependencies (manylinux x86_64, CPython 3.12)..."
python3 -m pip --version >/dev/null 2>&1 || {
  echo "ERROR: python3 -m pip is required to package Lambda deps." >&2
  exit 1
}
DEPS_DIR="$(mktemp -d)"
trap 'rm -rf "$DEPS_DIR"' EXIT
python3 -m pip install -q \
  --platform manylinux2014_x86_64 \
  --python-version 3.12 \
  --implementation cp \
  --abi cp312 \
  --only-binary=:all: \
  -r "$ROOT_DIR/backend/requirements-lambda.txt" \
  -t "$DEPS_DIR"
# Slim for the 250 MB Lambda limit (each verified unused on our paths):
# - boto3/botocore already ship in the python3.12 runtime;
# - sqlalchemy backs only langchain's SQL chains, which we don't use;
# - grpc + google protobufs back opensearchpy's async/gRPC transport,
#   which the sync SigV4 client we use never touches;
# - PIL backs only fpdf2 image embedding (our memos are text-only, and
#   every fpdf2 PIL import is TYPE_CHECKING- or try/except-guarded).
rm -rf "$DEPS_DIR/boto3" "$DEPS_DIR/botocore"
rm -rf "$DEPS_DIR"/boto3-*.dist-info "$DEPS_DIR"/botocore-*.dist-info
rm -rf "$DEPS_DIR/sqlalchemy" "$DEPS_DIR"/sqlalchemy-*.dist-info
rm -rf "$DEPS_DIR/grpc" "$DEPS_DIR/google" "$DEPS_DIR"/grpcio-*.dist-info
rm -rf "$DEPS_DIR"/googleapis_common_protos-*.dist-info
rm -rf "$DEPS_DIR"/opensearch_protobufs-*.dist-info
rm -rf "$DEPS_DIR"/protobuf-*.dist-info "$DEPS_DIR"/proto_plus-*.dist-info
rm -rf "$DEPS_DIR/PIL" "$DEPS_DIR/pillow.libs" "$DEPS_DIR"/Pillow-*.dist-info
for fn in ApiFunction IngestFunction; do
  cp -r "$DEPS_DIR"/. "$ROOT_DIR/.aws-sam/build/$fn/"
  SIZE_KB="$(du -sk "$ROOT_DIR/.aws-sam/build/$fn" | cut -f1)"
  if [ "$SIZE_KB" -gt 245760 ]; then
    echo "ERROR: $fn bundle is ${SIZE_KB}KB, over the 250MB Lambda limit." >&2
    exit 1
  fi
  echo "$fn bundle: ${SIZE_KB}KB"
done

sam deploy \
  --template-file "$ROOT_DIR/.aws-sam/build/template.yaml" \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --no-confirm-changeset \
  --no-fail-on-empty-changeset \
  --parameter-overrides "${OVERRIDES[@]}"

"$SCRIPT_DIR/status.sh"
