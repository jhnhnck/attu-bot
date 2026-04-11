#!/usr/bin/env bash
# run ruff format + check after editing a python file
set -euo pipefail

FILE=$(jq -r '.tool_input.file_path // ""')

[[ "$FILE" == *.py ]] || exit 0
[[ -f "$FILE" ]] || exit 0

ruff format "$FILE"
ruff check "$FILE"
