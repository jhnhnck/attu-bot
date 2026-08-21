---
name: file-header
description: AttuBot file header convention - SPDX license tag plus a structured breadcrumb docstring on every newly created source file. trigger when creating any new file under `apps/`, `packages/`, `tests/`, or `scripts/`; before writing the first line of a new `.py`, `.js`, `.ts`, `.sh`, `.zsh`, or `.bash` file; when using the `Write` tool to create a new source file; when answering questions about file headers, license markers, copyright notices, or SPDX in this repo. canonical source for the header format - docs/agents.md still describes the older verbose-docstring convention; when this skill diverges from agents.md, this skill wins and agents.md should be updated to match.
---

# file-header

Canonical reference when **creating a new source file** in this repo. This skill is canonical; update it directly. It supersedes the verbose docstring header described in `docs/agents.md` - flag that divergence so agents.md can be updated to match.

This skill applies to **new files only**. Do not retrofit existing files mid-task; bulk migration is a separate effort.

## the rule

Every new source file gets a two-part header:

1. an `SPDX-License-Identifier: Apache-2.0` line in the language's comment syntax
2. for python only: a one-line module docstring of the form `<dotted module path> | <short lowercase description>.`

Nothing else. No author line, no copyright year, no license prose, no decorative dividers above or below.

## by language

### python (`.py`)

```python
# SPDX-License-Identifier: Apache-2.0
"""<module path> | <short description>."""

import ...
```

The docstring must be the **first statement** after the SPDX comment - `ruff format` and `basedpyright` both expect it there, and PEP 257 picks it up as the module docstring.

Real examples:

```python
# SPDX-License-Identifier: Apache-2.0
"""doombot.commands | egg game slash commands - loaded dynamically on hatch day."""
```

```python
# SPDX-License-Identifier: Apache-2.0
"""doombot.client | discord client entry point."""
```

```python
# SPDX-License-Identifier: Apache-2.0
"""doombot.database.repositories | repository pattern for guild config, years, eggs."""
```

### javascript / typescript (`.js`, `.ts`, `.mjs`, `.cjs`, `.tsx`)

SPDX only - no breadcrumb, no description. JS/TS has no native module-docstring concept and the file path already names the module.

```javascript
// SPDX-License-Identifier: Apache-2.0

import { initGuildToggle } from './components/guild-toggle.js';
```

```typescript
// SPDX-License-Identifier: Apache-2.0

import { test, expect } from '@playwright/test';
```

### shell (`.sh`, `.zsh`, `.bash`)

Shebang first, then SPDX, then any usage / purpose comment block (these earn their keep on scripts where users invoke `--help`-less commands).

```bash
#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# usage: bash scripts/create_dev_seed.sh <backup.tar.bz2>
# strips large bot-only collections to keep the seed small for web dev.
set -e
```

```zsh
#!/usr/bin/env zsh
# SPDX-License-Identifier: Apache-2.0
# migrates the postgres_data volume to a new server. run from the prod project dir.
set -euo pipefail
```

### other formats

- HTML: `<!-- SPDX-License-Identifier: Apache-2.0 -->` on the first line, before `<!DOCTYPE html>` is fine
- CSS: `/* SPDX-License-Identifier: Apache-2.0 */`
- TOML / YAML / `.env`: **no header**. SPDX in config files is unusual and the parsers don't always tolerate leading comments uniformly. The repo's `LICENSE` file covers them.
- Markdown, JSON, `.gitignore`, `.dockerignore`: no header.

## how to derive the breadcrumb

The breadcrumb is the **importable python module path** that this file's contents extend or define:

| file path | breadcrumb |
|---|---|
| `apps/bot/doombot/commands/eggs.py` | `doombot.commands.eggs` |
| `apps/bot/doombot/commands/__init__.py` | `doombot.commands` |
| `apps/bot/doombot/client/__init__.py` | `doombot.client` |
| `apps/bot/doombot/database/repositories.py` | `doombot.database.repositories` |
| `packages/shared-models/shared_models/year.py` | `shared_models.year` |
| `tests/python/unit/test_eggs.py` | `tests.unit.test_eggs` |
| `scripts/deploy.py` | `scripts.deploy` |

Rules:

- start from the package root (the directory containing the package's `__init__.py` or that's listed in the workspace's `pyproject.toml`), not from the repo root
- for `__init__.py`, use the package's own dotted path - **do not** include `__init__` in the breadcrumb
- for every other `.py` file, the breadcrumb is its full importable module path including the file basename (without `.py`)
- the breadcrumb is always lowercase with `.` separators - matches what you'd type after `import`

Note: the project is mid-rename from `attubot` to `doombot` (see the workspace layout commit). When creating files under `apps/bot/attubot/...`, use the package name as it currently stands in `pyproject.toml` for that workspace, not the future name. If the package is currently `attubot`, the breadcrumb is `attubot.commands.eggs`.

## description style

- **lowercase**, matching the comment-style and notes/ aesthetic
- **brief** - one short clause; expand with a `-` (regular dash) only when a single clause is genuinely insufficient
- **end with a period** - PEP 257 requires it on one-line docstrings; this is the only place in the codebase where trailing periods on otherwise-comment-like text are correct
- **no implementation details** - say what the module *is*, not how it works
- **no references** to issue numbers, PRs, or "added for X" - those rot

```python
# good
"""doombot.commands | egg game slash commands - loaded dynamically on hatch day."""

# bad - capitalized
"""doombot.commands | Egg game slash commands."""

# bad - no period
"""doombot.commands | egg game slash commands"""

# bad - restates the breadcrumb
"""doombot.commands | the eggs commands module."""

# bad - implementation detail
"""doombot.commands | egg game slash commands using SlashCommandGroup."""

# bad - issue reference (will rot)
"""doombot.commands | egg game slash commands (added for #142)."""
```

## what's explicitly dropped from the old style

- **author line** (`Author(s): @jhnhnck <john@jhnhnck.com>`): gone. git blame is the source of truth.
- **license prose** (`This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.`): gone. SPDX replaces it.
- **project name prefix** (`AttuBot - <description>`): gone. the breadcrumb tells you the package.
- **per-file copyright year**: never added. project-wide copyright lives in `LICENSE` only.

## not in scope for this skill

- **existing files**: don't rewrite headers as part of unrelated work. a deliberate one-shot migration touches every file at once and lands as its own commit.
- **generated files**: if a file is genuinely generated (none in this repo today), use the generator's convention (e.g. `# Code generated by X; DO NOT EDIT.` on line 1, then SPDX). nothing in this repo currently triggers this.
- **`wip/` and `*.wip.py` files**: excluded from linting per `docs/agents.md`. headers optional - skip them for scratch work.
- **vendored third-party code**: keep the upstream's header verbatim; do not impose this skill's format on code we didn't write.

## tooling notes

- `ruff format` and `ruff check`: both happy with `# comment` then `"""docstring"""` as the first two statements
- `basedpyright`: treats the docstring as the module docstring, picks it up on hover
- `pydoc doombot.commands.eggs` and `help(doombot.commands.eggs)`: both show the breadcrumb-and-description line
- license scanners (REUSE, ScanCode, FOSSology, GitHub): all detect `SPDX-License-Identifier:` natively

## checklist before saving a new file

1. is the SPDX line the first non-shebang line? (line 1 for `.py`/`.js`/`.ts`; line 2 for shell after the shebang)
2. for `.py`: is the docstring the next statement, with the right breadcrumb and a period at the end?
3. is the description lowercase and free of implementation/issue references?
4. is there a blank line between the header and the first import / first code statement?

If yes to all four, the header is correct.

## cross-references

- `docs/agents.md` "file header (required on every python file)" section - currently shows the older verbose form; flag for update when this skill is adopted
- `comment-style` skill - lowercase / no-trailing-period rules apply to every other comment in the file (the docstring is the one exception)
- `LICENSE` at repo root - the actual Apache 2.0 license text
- `wip/file_headers.md` - the brainstorm that arrived at this style; not authoritative once adopted
