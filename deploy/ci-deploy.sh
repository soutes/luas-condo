#!/usr/bin/env bash
# Runs on the GitHub Actions runner: opens an SSH session to the VM and executes
# deploy/deploy.sh there. Everything comes from environment variables (never
# interpolate workflow inputs into the shell line):
#   DEPLOY_HOST, DEPLOY_USER, DEPLOY_SSH_KEY, DEPLOY_KNOWN_HOSTS  (secrets, required)
#   DEPLOY_PATH   (optional, default /opt/luas-condo)
#   DEPLOY_TARGET ("main" or a commit sha)
set -euo pipefail

for var in DEPLOY_HOST DEPLOY_USER DEPLOY_SSH_KEY DEPLOY_KNOWN_HOSTS DEPLOY_TARGET; do
  if [ -z "${!var:-}" ]; then
    echo "Missing required setting: $var (configure it as a repository/environment secret)" >&2
    exit 1
  fi
done

DEPLOY_PATH="${DEPLOY_PATH:-/opt/luas-condo}"
if ! printf '%s' "$DEPLOY_PATH" | grep -Eq '^/[A-Za-z0-9_./-]+$'; then
  echo "Invalid DEPLOY_PATH" >&2
  exit 1
fi
if [ "$DEPLOY_TARGET" != "main" ] && ! printf '%s' "$DEPLOY_TARGET" | grep -Eq '^[0-9a-fA-F]{7,40}$'; then
  echo "Invalid DEPLOY_TARGET: expected 'main' or a commit sha" >&2
  exit 1
fi

umask 077
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
printf '%s\n' "$DEPLOY_SSH_KEY" > "$workdir/id"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$workdir/known_hosts"

ssh -i "$workdir/id" \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$workdir/known_hosts" \
  -o ServerAliveInterval=30 \
  "$DEPLOY_USER@$DEPLOY_HOST" \
  "DEPLOY_PATH='$DEPLOY_PATH' bash -s -- '$DEPLOY_TARGET'" < deploy/deploy.sh
