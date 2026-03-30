#!/usr/bin/env bash
# run ruff format + check after editing a python file
set -euo pipefail

FILE=$(python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null || true)

[[ "$FILE" == *.py ]] || exit 0
[[ -f "$FILE" ]] || exit 0

ruff format "$FILE"
ruff check "$FILE"
