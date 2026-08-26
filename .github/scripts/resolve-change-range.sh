#!/usr/bin/env bash
set -euo pipefail

if [ "${EVENT_NAME:-}" = "pull_request" ]; then
  BASE_SHA="${PR_BASE_SHA:-}"
  DIFF_RANGE="$BASE_SHA...HEAD"
elif [ "${EVENT_NAME:-}" = "push" ] && [ -n "${PUSH_BEFORE_SHA:-}" ] && ! [[ "$PUSH_BEFORE_SHA" =~ ^0+$ ]]; then
  BASE_SHA="$PUSH_BEFORE_SHA"
  DIFF_RANGE="$BASE_SHA..HEAD"
else
  echo "::error::Cannot determine a safe full change range for ${EVENT_NAME:-unknown event}"
  exit 1
fi

if ! git cat-file -e "${BASE_SHA}^{commit}"; then
  echo "::error::Change-range base is not an available commit: $BASE_SHA"
  exit 1
fi

if [ -z "${GITHUB_ENV:-}" ]; then
  echo "::error::GITHUB_ENV is required to export the resolved change range"
  exit 1
fi

{
  echo "BASE_SHA=$BASE_SHA"
  echo "DIFF_RANGE=$DIFF_RANGE"
} >> "$GITHUB_ENV"
echo "Using full change range: $DIFF_RANGE"
