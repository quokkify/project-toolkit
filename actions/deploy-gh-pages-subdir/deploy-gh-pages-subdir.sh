#!/usr/bin/env bash
# Publish one workspace directory into a subdirectory on a GitHub Pages branch.
set -euo pipefail

error() {
  echo "::error::$*" >&2
  exit 2
}

[[ -n "${INPUT_TOKEN:-}" ]] || error "token is required"
[[ -n "${GITHUB_WORKSPACE:-}" && -d "$GITHUB_WORKSPACE" ]] || error "GITHUB_WORKSPACE must point to an existing directory"
[[ -n "${GITHUB_REPOSITORY:-}" ]] || error "GITHUB_REPOSITORY is required"

validate_relative_path() {
  local value="$1"
  local label="$2"
  case "$value" in
    ""|/*|.|./*|*/./*|..|../*|*/../*|*/..) error "$label must be a safe relative path" ;;
  esac
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || error "$label must not contain newlines"
}

validate_relative_path "$INPUT_PUBLISH_DIR" "publish-dir"
validate_relative_path "$INPUT_DESTINATION_DIR" "destination-dir"

BRANCH="${INPUT_BRANCH:-gh-pages}"
[[ "$BRANCH" =~ ^[A-Za-z0-9._/-]+$ ]] || error "branch contains unsupported characters"
[[ "$BRANCH" != -* && "$BRANCH" != */ && "$BRANCH" != */. && "$BRANCH" != *..* && "$BRANCH" != *'@{'* ]] || error "branch is not a safe Git ref"

PUB="$(
  cd "$GITHUB_WORKSPACE"
  python3 - "$INPUT_PUBLISH_DIR" <<'PY'
import os
import sys

candidate = os.path.abspath(sys.argv[1])
workspace = os.path.abspath(os.getcwd())
if os.path.commonpath((candidate, workspace)) != workspace:
    raise SystemExit("publish-dir resolves outside GITHUB_WORKSPACE")
print(candidate)
PY
)"
[[ -d "$PUB" ]] || error "publish-dir not found: $INPUT_PUBLISH_DIR"

# Keep credentials out of command-line arguments and the generated remote URL.
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=http.extraheader
export GIT_CONFIG_VALUE_0="Authorization: Bearer ${INPUT_TOKEN}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
REPO_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}.git"
git clone --quiet "$REPO_URL" "$WORK/repo"
R="$WORK/repo"
cd "$R"

if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git fetch --quiet origin "$BRANCH:$BRANCH"
  git checkout --quiet "$BRANCH"
else
  git checkout --quiet --orphan "$BRANCH"
  git rm -rf --quiet . 2>/dev/null || true
fi

mkdir -p "$R/$INPUT_DESTINATION_DIR"
rsync -a --delete "$PUB/" "$R/$INPUT_DESTINATION_DIR/"
touch "$R/.nojekyll"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A

if git diff --cached --quiet; then
  echo "No changes to push to $BRANCH."
  exit 0
fi

git commit --quiet -m "docs(pages): deploy $INPUT_DESTINATION_DIR"

# Re-read the remote tip and lease the update. A single retry handles a concurrent
# publisher without overwriting a sibling deployment or silently losing its update.
for attempt in 1 2; do
  expected_sha="$(git ls-remote --heads origin "$BRANCH" | awk 'NR == 1 { print $1 }')"
  if [[ -n "$expected_sha" ]]; then
    git fetch --quiet origin "$BRANCH"
    git rebase --quiet "origin/$BRANCH"
    git push --quiet --force-with-lease="refs/heads/$BRANCH:$expected_sha" origin "HEAD:$BRANCH" && exit 0
  else
    git push --quiet --force-with-lease="refs/heads/$BRANCH:" origin "HEAD:$BRANCH" && exit 0
  fi
  if [[ "$attempt" == 1 ]]; then
    echo "Concurrent update detected; retrying gh-pages push." >&2
  fi
done

error "unable to publish $INPUT_DESTINATION_DIR after a concurrent update"
