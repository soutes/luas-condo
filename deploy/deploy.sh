#!/usr/bin/env bash
# Deploys (or rolls back) the LuasCondo stack on the VM. Executed ON the VM, normally
# piped over SSH by deploy/ci-deploy.sh:   ssh host 'bash -s -- <target>' < deploy/deploy.sh
#
#   <target> = "main"            -> fast-forward to origin/main
#            = <commit sha>      -> that exact commit (rollback); if it is the tip of
#                                   origin/main the clone stays on the main branch
#
# After rebuilding it waits for /api/health. If the new version never becomes healthy,
# it automatically restores the previous commit and exits non-zero.
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/luas-condo}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${BACKEND_HOST_PORT:-8000}/api/health}"
HEALTH_TRIES="${HEALTH_TRIES:-60}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-10}"

target="${1:-}"
if [ "$target" != "main" ] && ! printf '%s' "$target" | grep -Eq '^[0-9a-fA-F]{7,40}$'; then
  echo "Invalid target '$target': expected 'main' or a commit sha (7-40 hex chars)" >&2
  exit 2
fi

cd "$DEPLOY_PATH"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Working tree on the VM has local modifications; refusing to deploy." >&2
  git status --short >&2
  exit 3
fi

previous="$(git rev-parse HEAD)"
git fetch --prune origin

checkout_commit() {
  local sha="$1"
  git cat-file -e "${sha}^{commit}"
  if [ "$(git rev-parse "$sha")" = "$(git rev-parse origin/main)" ]; then
    git checkout --quiet main
    git merge --ff-only origin/main
  else
    git checkout --quiet --detach "$sha"
  fi
}

wait_healthy() {
  local i
  for i in $(seq 1 "$HEALTH_TRIES"); do
    if curl -fsS -m 10 "$HEALTH_URL" >/dev/null 2>&1; then
      echo "Healthy after attempt $i"
      return 0
    fi
    sleep "$HEALTH_INTERVAL"
  done
  return 1
}

rebuild() {
  docker compose build backend frontend || docker compose build backend frontend
  docker compose up -d
  docker compose ps
}

if [ "$target" = "main" ]; then
  git checkout --quiet main
  git merge --ff-only origin/main
else
  checkout_commit "$target"
fi
current="$(git rev-parse HEAD)"
echo "Deploying $current (previous: $previous)"

rebuild
if wait_healthy; then
  echo "Deploy OK: $current"
  exit 0
fi

echo "New version unhealthy; rolling back to $previous" >&2
docker compose logs --tail 40 backend >&2 || true
if [ "$previous" != "$current" ]; then
  git checkout --quiet --detach "$previous"
  rebuild
  wait_healthy || echo "Rollback is also unhealthy; manual intervention needed" >&2
fi
exit 1
