#!/usr/bin/env bash
# prepend pyenv doom-bot activation to python-related bash commands
set -euo pipefail

INPUT=$(cat)
COMMAND=$(python3 -c "import sys, json; d=json.loads(sys.argv[1]); print(d.get('tool_input', {}).get('command', ''))" "$INPUT" 2>/dev/null || true)

# only intercept python-related commands
if ! echo "$COMMAND" | grep -qE '^\s*(python[0-9.]?|ruff|pytest|pip[0-9.]?|uv)\b'; then
  exit 0
fi

PYENV_INIT="export PYENV_ROOT=/home/jhn/.pyenv && export PATH=\"\$PYENV_ROOT/bin:\$PYENV_ROOT/shims:\$PATH\" && export PYENV_VERSION=doom-bot"
MODIFIED="$PYENV_INIT && $COMMAND"

python3 -c "
import sys, json
d = json.loads(sys.argv[1])
d['tool_input']['command'] = sys.argv[2]
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'allow',
        'updatedInput': d['tool_input']
    }
}))
" "$INPUT" "$MODIFIED"

exit 0
