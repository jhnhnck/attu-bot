---
name: file-header
description: AttuBot file header convention - SPDX license tag plus a structured breadcrumb docstring on every newly created source file. trigger when creating any new file under `apps/`, `packages/`, `tests/`, or `scripts/`; before writing the first line of a new `.py`, `.js`, `.ts`, `.sh`, or `.zsh` file; when answering questions about file headers, license markers, or SPDX in this repo. canonical source for the header format.
---

# file-header (AttuBot overlay)

read `~/.claude/skills/file-header/SKILL.md` once for the structure. this skill is canonical for AttuBot; update it directly.

project parameters:
- **license**: `Apache-2.0`
- **separator**: pipe (`|`)
- **breadcrumb**: dotted importable python module path (see derivation rules below)

## python examples

```python
# SPDX-License-Identifier: Apache-2.0
"""doombot.commands | egg game slash commands - loaded dynamically on hatch day."""
```

```python
# SPDX-License-Identifier: Apache-2.0
"""doombot.client | discord client entry point."""
```

## breadcrumb derivation

the breadcrumb is the **importable python module path** starting from the package root:

| file path | breadcrumb |
|---|---|
| `apps/bot/doombot/commands/eggs.py` | `doombot.commands` (via `eggs`) |
| `apps/bot/doombot/commands/__init__.py` | `doombot.commands` |
| `apps/bot/doombot/client/__init__.py` | `doombot.client` |
| `packages/shared-models/shared_models/year.py` | `shared_models.year` |
| `tests/python/unit/test_eggs.py` | `tests.unit.test_eggs` |

- start from the package root (directory containing `__init__.py` or listed in workspace `pyproject.toml`)
- for `__init__.py`: use the package's own dotted path, do not include `__init__`
- always lowercase with `.` separators

note: the project is mid-rename from `attubot` to `doombot`; use the package name as it currently stands in `pyproject.toml` for that workspace.

## javascript / typescript / shell

same as global: SPDX-only for JS/TS, shebang-then-SPDX for shell.

## cross-references

- `CLAUDE.md` - project rules and personality conventions the header text follows
- `comment-style` - lowercase rules (the docstring period is the one exception)
- `LICENSE` - the Apache 2.0 text
