---
name: docs-cleanup
description: Clean up markdown files under docs/ - remove obsolete sections, fix stale cross-references, update outdated path references, and strip phrases that aren't about the current state of the project. Trigger on "clean up docs", "docs cleanup", "fix stale docs", "update docs references", "remove obsolete sections", "tidy docs"; when docs reference old file paths (doom_bot/, notes/agents.md, agents.md), removed files, or superseded systems; when a docs pass is needed before or after a plan phase. Not for Python source files (see code-cleanup). Not for rewriting content or changing meaning.
argument-hint: [file-path | directory]
allowed-tools: Read Edit Bash(find * -name "*.md") Bash(grep -rn *)
---

# docs-cleanup

Clean one or more docs/ markdown files of stale references, obsolete sections, and outdated paths — zero content rewrites.

**Target**: `$ARGUMENTS` — a file path or directory (recurse into all `.md` files). If no argument, apply to all `.md` files under `docs/`.

---

## what gets cleaned

### stale cross-references

`agents.md` was the old root guidance file. Its content was split across two destinations when replaced:

- rules, personality, style conventions → `CLAUDE.md`
- architecture, package tables, file layout → `docs/architecture.md`

When a doc references `agents.md` (or `notes/agents.md`), check the surrounding context to pick the right redirect:

| if the citation is about… | redirect to |
|---|---|
| rules, noqa policy, comment/commit style, personality | `CLAUDE.md` |
| package layout, file tables, module roles | `docs/architecture.md` |
| config system | `docs/config-system.md` |
| a named feature | `docs/features/<feature>.md` |

Known case: `docs/nova-core.md` links to `agents.md` (which no longer exists); the link text describes architecture → update to `docs/architecture.md`.

Other common stale forms and their redirects:

| stale | current |
|---|---|
| `notes/agents.md` | context-dependent (see table above) |
| `notes/<file>.md` | `docs/<file>.md` |
| `agents.md rule #N` | `CLAUDE.md rule #N` |

When a link targets a file that no longer exists and a redirect is unknown, remove the link text and keep surrounding prose if it still makes sense; delete the sentence if it only existed to point elsewhere.

### stale path references

Old package layout (`doom_bot/`) was replaced by the current monorepo layout. Update references on sight:

| stale | current |
|---|---|
| `doom_bot/` | `apps/bot/nova_core/` or `apps/bot/` (check actual location) |
| `doom_bot/commands/` | `apps/bot/nova_core/commands/` |
| `doom_bot/client/` | `apps/bot/nova_core/client/` |
| `doom_bot/database/` | `packages/shared-models/attu_models/` |
| `doom_bot/config.py` | `apps/bot/nova_core/config.py` |
| `doom_bot/web/` | `apps/server/` |
| `doom_bot/wiki/` | `packages/attu-wiki/` |

When a reference is to a coverage snapshot or historical log (see `docs/coverage.md`), do not update it — those are historical records. Leave a note if the file is entirely stale and should be pruned.

### obsolete sections

Remove a section when it describes a system or workflow that no longer exists and has no bearing on current operation. Common cases:

- sections describing the old `notes/agents.md` doc system (replaced by CLAUDE.md + mkdocs)
- changelog entries in doc files that describe pre-mkdocs restructuring (keep post-mkdocs entries)
- sections describing dev workflow steps that are now in `CLAUDE.md` or handled by the harness
- "see agents.md for X" paragraphs where agents.md no longer exists

Do not remove sections just because they're short or feel redundant - only remove if the described system is gone.

### `.meta.md` handling

`docs/.meta.md` describes the old `notes/agents.md` system. It is now a historical artifact. Do not delete it, but if tasked with cleanup on this file specifically:
- the changelog and metadata sections are worth keeping as history
- the prescriptive instructions ("how to structure agents.md") are obsolete; flag for human review rather than auto-removing

### broken links

Fix mkdocs-style relative links (`[text](file.md)`) that point to files that have moved or been renamed. Common breakage:
- `agents.md` → no equivalent (link to `CLAUDE.md` if the context fits, otherwise remove)
- `notes/style/` → `docs/style/`
- `notes/features/` → `docs/features/`
- `notes/dev/` → `docs/dev/`

### metadata sections

Each doc file ends with a `## metadata` block containing `last_updated`. Update the date to today when making other changes to the file.

---

## workflow

1. **discover files** — if `$ARGUMENTS` is a directory, run `find $ARGUMENTS -name "*.md" | sort` and process the list. if a single file, process it directly. skip hidden files unless explicitly targeted.
2. **read each file** — scan for the patterns above without editing yet.
3. **apply all fixes in one Edit pass per file** — batch changes per file.
4. **report** — after all files, emit a summary.

---

## reporting

After cleanup, report:

- **files changed**: N / total
- **by category**: stale refs, path updates, removed sections, broken links, metadata updates
- **flagged for human review**: sections that are probably obsolete but require a judgment call (e.g. `.meta.md` prescriptive content, historical coverage snapshots, doc files that may need broader rewrite)

If nothing needed fixing in a file, say so briefly.

---

## what NOT to touch

- content meaning - do not rewrite sentences, only fix references and remove dead sections
- historical records (`docs/coverage.md` table, plan log files)
- `docs/.meta.md` prescriptive sections without explicit instruction
- `wip/` files
- code blocks inside docs (don't "fix" paths that appear inside code examples unless they're clearly wrong)
- mkdocs nav entries in `mkdocs.yml` — that's a separate task

---

## cross-references

- `code-cleanup` global skill — equivalent cleanup for Python source files
- `comment-style` project skill — python comment conventions
- `mkdocs.yml` — authoritative nav structure; use to verify what files actually exist
