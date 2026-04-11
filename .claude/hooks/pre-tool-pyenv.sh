#!/usr/bin/env bash
# source uv venv and allow python-related bash commands
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# only intercept python-related commands
if ! echo "$COMMAND" | grep -qE '^\s*(python[0-9.]?|ruff|pytest|pip[0-9.]?|uv|basedpyright)\b'; then
  exit 0
fi

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$HOOK_DIR")")"
UV_INIT="source $PROJECT_ROOT/.venv/bin/activate"
MODIFIED="$UV_INIT && $COMMAND"

echo "$INPUT" | jq --arg cmd "$MODIFIED" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "allow",
    updatedInput: (.tool_input | .command = $cmd)
  }
}'

exit 0
