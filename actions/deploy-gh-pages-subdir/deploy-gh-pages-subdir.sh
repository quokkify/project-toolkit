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

RETENTION_COUNT="${INPUT_RETENTION_COUNT:-0}"
[[ "$RETENTION_COUNT" =~ ^[0-9]+$ ]] || error "retention-count must be a non-negative integer"
RETENTION_COUNT=$((10#$RETENTION_COUNT))
if (( RETENTION_COUNT > 0 )); then
  retention_dest_name="${INPUT_DESTINATION_DIR##*/}"
  [[ "$retention_dest_name" =~ ^pr-[0-9]+$ ]] || error "retention-count requires destination-dir basename pr-N"
fi

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
token_var=INPUT_TOKEN
export GIT_CONFIG_VALUE_0="Authorization: Bearer ${!token_var}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
REPO_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}.git"
git clone --quiet --no-checkout "$REPO_URL" "$WORK/repo"
R="$WORK/repo"
cd "$R"

if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  git fetch --quiet origin "$BRANCH"
  git checkout --quiet -B "$BRANCH" "origin/$BRANCH"
else
  git checkout --quiet --orphan "$BRANCH"
  git rm -rf --quiet . 2>/dev/null || true
fi

mkdir -p "$R/$INPUT_DESTINATION_DIR"
rsync -a --delete "$PUB/" "$R/$INPUT_DESTINATION_DIR/"

prune_old_reports() {
  (( RETENTION_COUNT > 0 )) || return 0

  local parent dest_name candidate rel timestamp
  parent="${INPUT_DESTINATION_DIR%/*}"
  [[ "$parent" != "$INPUT_DESTINATION_DIR" ]] || parent="."

  local -a entries=()
  for candidate in "$R/$parent"/pr-*; do
    [[ -d "$candidate" ]] || continue
    dest_name="${candidate##*/}"
    [[ "$dest_name" =~ ^pr-[0-9]+$ ]] || continue
    rel="${parent%/.}/$dest_name"
    [[ "$parent" != "." ]] || rel="$dest_name"
    if [[ "$rel" == "$INPUT_DESTINATION_DIR" ]]; then
      timestamp="$(date +%s)"
    else
      timestamp="$(git log -1 --format=%ct -- "$rel" 2>/dev/null || true)"
      [[ "$timestamp" =~ ^[0-9]+$ ]] || timestamp=0
    fi
    entries+=("${timestamp}"$'\t'"${rel}")
  done

  local -a keep=()
  while IFS=$'\t' read -r timestamp rel; do
    [[ -n "$rel" ]] || continue
    if (( ${#keep[@]} < RETENTION_COUNT )); then
      keep+=("$rel")
    else
      echo "Pruning old gh-pages report: $rel"
      rm -rf -- "${R:?}/${rel:?}"
    fi
  done < <(printf '%s\n' "${entries[@]}" | sort -t $'\t' -k1,1nr -k2,2)
}

prune_old_reports
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
