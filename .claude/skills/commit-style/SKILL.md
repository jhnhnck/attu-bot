---
name: commit-style
description: AttuBot commit message conventions. trigger before drafting, writing, or proposing any commit message; when running `git commit`, `git status`, or `git diff` in preparation for a commit; when staging hunks for a commit; when answering questions about commit format, types, scope, or what belongs in a single commit.
---

# commit-style (AttuBot overlay)

read `~/.claude/skills/commit-style/SKILL.md` once for the universal rules (format, types, description style, background-session exception). this skill is canonical for AttuBot; update it directly.

project-specific additions below.

## examples to pattern-match against

```
fix(hatch): enable one week early; i'm impatient :tieteran:
fix(wiki): lookup buttons don't die on restart
fix(modlog): bot users were ignored in kick/ban messages
feat(hatch): trading and collection info
patch(hatch): fix up responses and progress message length
feat(hatch): less aggressive trade timeout
feat(hatch): no more screaming snakes
chore: oops all linting fixes
```

note: `feat(hatch): trading and collection info` - not "implement trading and collection info". `fix(wiki): lookup buttons don't die on restart` - describes the bug, not the fix.

## what makes a unit complete

- **`feat`** - implementation + tests + notes/docs + config/assets + `docs/to-do.md` updates, all in one commit; done means it works, not just compiles
- **`fix` / `patch`** - change + test; `docs/to-do.md` updates marking the item complete go in the same commit
- **`refactor`** - every file referencing the renamed/reshaped thing, swept in one commit; no partial refactors left dangling
- **`test`** - if a feature ships without tests, add a `docs/to-do.md` entry under the test section

## cross-references

- `docs/agents.md` rule #3 - the no-unprompted-commits rule
- `docs/agents.md` personality section - semicolons or regular dashes, american english, brief
- `feature-completion` - pre-commit checklist
