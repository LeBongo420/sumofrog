#!/usr/bin/env bash
# Remove target/deploy/sumofrog-keypair.json only when it is a plain stray
# file: not a symlink, link count 1, realpath inside this repo's real
# target/deploy, and neither target/ nor target/deploy is a symlink.
# Otherwise warn and leave it. Uses plain rm, never shred.
# Usage: scripts/remove_stray_keypair.sh [REPO_ROOT]
set -euo pipefail

ROOT="${1:-.}"
if [ ! -d "$ROOT" ]; then
  echo "warning: leaving target/deploy/sumofrog-keypair.json in place (repo root is not a directory)" >&2
  exit 0
fi
ROOT="$(cd "$ROOT" && pwd)"
REPO_REAL="$(realpath "$ROOT")"

REL="target/deploy/sumofrog-keypair.json"
TARGET="$ROOT/target"
DEPLOY="$ROOT/target/deploy"
KEY="$DEPLOY/sumofrog-keypair.json"

if [ ! -e "$KEY" ] && [ ! -L "$KEY" ]; then
  exit 0
fi

warn() {
  echo "warning: leaving $REL in place ($1)" >&2
}

if [ -L "$TARGET" ]; then
  warn "target is a symlink"
  exit 0
fi
if [ -L "$DEPLOY" ]; then
  warn "target/deploy is a symlink"
  exit 0
fi
if [ ! -d "$DEPLOY" ]; then
  warn "target/deploy is not a directory"
  exit 0
fi
if [ -L "$KEY" ]; then
  warn "it is a symlink"
  exit 0
fi
if [ ! -f "$KEY" ]; then
  warn "it is not a regular file"
  exit 0
fi

LINKS="$(stat -c '%h' "$KEY")"
if [ "$LINKS" != 1 ]; then
  warn "link count is $LINKS"
  exit 0
fi

DEPLOY_REAL="$(realpath "$DEPLOY")"
KEY_REAL="$(realpath "$KEY")"
if [ "$DEPLOY_REAL" != "$REPO_REAL/target/deploy" ]; then
  warn "target/deploy real path is not the repo's target/deploy"
  exit 0
fi
case "$KEY_REAL" in
  "$DEPLOY_REAL"/*) ;;
  *)
    warn "its real path is outside target/deploy"
    exit 0
    ;;
esac

rm -- "$KEY"
