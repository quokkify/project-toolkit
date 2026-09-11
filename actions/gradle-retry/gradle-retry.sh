#!/usr/bin/env bash
# Run a Gradle command with bounded recovery for transient resolution failures.
# 429 failures retain exponential retry; a not-found failure gets one refresh.
set -uo pipefail

command_string="${GRADLE_RETRY_COMMAND:-}"
max_attempts="${GRADLE_RETRY_MAX_ATTEMPTS:-3}"
delay="${GRADLE_RETRY_INITIAL_DELAY_SECONDS:-30}"

if [[ -z "$command_string" ]]; then
  echo "gradle-retry.sh: GRADLE_RETRY_COMMAND is required" >&2
  exit 2
fi
if ! [[ "$max_attempts" =~ ^[1-9][0-9]*$ ]]; then
  echo "gradle-retry.sh: GRADLE_RETRY_MAX_ATTEMPTS must be a positive integer, got '${max_attempts}'" >&2
  exit 2
fi
if ! [[ "$delay" =~ ^[1-9][0-9]*$ ]]; then
  echo "gradle-retry.sh: GRADLE_RETRY_INITIAL_DELAY_SECONDS must be a positive integer, got '${delay}'" >&2
  exit 2
fi

attempt=1
refresh_attempted=0
while true; do
  output="$(mktemp)"
  bash -euo pipefail -c "$command_string" 2>&1 | tee "$output"
  status=${PIPESTATUS[0]}

  if [[ "$status" -eq 0 ]]; then
    rm -f "$output"
    exit 0
  fi

  is_repository_failure=0
  grep -qE 'Could not (GET|HEAD|resolve)' "$output" && is_repository_failure=1
  is_429=0
  grep -qE 'status code 429|429 Too Many Requests|Too Many Requests' "$output" && is_429=1

  if [[ "$is_repository_failure" -eq 1 && "$is_429" -eq 1 && "$attempt" -lt "$max_attempts" ]]; then
    jitter=$(( RANDOM % (delay / 3 + 1) ))
    sleep_for=$(( delay + jitter ))
    echo "::warning::Gradle failed with a transient repository 429 (attempt ${attempt}/${max_attempts}). Retrying in ${sleep_for}s..."
    rm -f "$output"
    sleep "$sleep_for"
    attempt=$((attempt + 1))
    delay=$((delay * 3))
    continue
  fi

  is_not_found=0
  grep -qE 'Could not find .+' "$output" && is_not_found=1
  if [[ "$is_not_found" -eq 1 && "$refresh_attempted" -eq 0 && "$command_string" != *--refresh-dependencies* ]]; then
    refresh_attempted=1
    command_string="$command_string --refresh-dependencies"
    echo "::warning::Gradle dependency resolution failed; retrying once with --refresh-dependencies."
    rm -f "$output"
    continue
  fi

  rm -f "$output"
  exit "$status"
done
