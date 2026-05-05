---
name: commit-style
description: AttuBot commit message conventions. trigger before drafting, writing, or proposing any commit message; when running `git commit`, `git status`, or `git diff` in preparation for a commit; when staging hunks for a commit; when answering questions about commit format, types, scope, or what belongs in a single commit.
---

# commit-style

Authoritative reference when preparing a commit in this repo. This skill is canonical; update it directly.

## The hard rule, first

**Never run `git commit` without explicit instruction in the current turn.** Even if the user told you to commit earlier in the conversation, ask for confirmation immediately before each `git commit`. This is rule #3 from `agents.md`; it is not optional and does not expire.

If the user says "commit this" you may stage and draft the message; pause and confirm before invoking `git commit`.

## Format

```
type(scope): description
```

- All lowercase. No body. No trailing period.
- `scope` is the single most relevant area touched; pick the primary, do not list multiple.
- Personality rules from `agents.md` apply: semicolons or regular dashes only (never em-dashes), American English.

## Types

| type | when |
|---|---|
| `feat` | additions; also removals and intentional behavior changes (often framed negatively or ironically) |
| `fix` | an actual bug |
| `patch` | minor non-bug tweak (wording, small tuning, typo) |
| `refactor` | code reshape with no behavior change; sweeps every reference in one commit |
| `chore` | linting, formatting, housekeeping; **always isolated** from other work |
| `test` | tests added on their own (tests can also ride with the feat that introduced them) |

`fix` vs `patch` is the distinction most often gotten wrong: if it wasn't broken, it's a `patch`.

## Description style

Plain noun phrases or casual statements. Describe **what changed**, not what was done to achieve it.

**Forbidden** — formal imperatives like "implement", "introduce", "centralize", "add support for", "ensure", "refactor X to Y". The model defaults to these; resist.

Personality and humor are welcome where they fit naturally; do not force them.

## Examples to pattern-match against

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

Note: `feat(hatch): trading and collection info` — not "implement trading and collection info". `fix(wiki): lookup buttons don't die on restart` — describes the bug, not the fix.

## What makes a unit complete

A commit ships when the unit it describes is whole. The shape of "whole" depends on the type:

- **`feat`** — implementation + tests + notes/docs + config/assets + `notes/to-do.md` updates, all in one commit. Done means the thing it describes works, not that the code compiles.
- **`fix` / `patch`** — the change plus any test that covers it. If db layer or a script had to be touched to make it right, those go in too. `notes/to-do.md` updates marking the item complete go in the same commit.
- **`refactor`** — every file referencing the renamed/reshaped thing, swept in a single commit. No partial refactors left dangling.
- **data / config change** — minimal: just the value and its docs.
- **`chore`** — never rides along with feature or fix work; collect linting and formatting separately.
- **`test`** — fine to include with the feature it covers, fine to land standalone later. If a feature ships without tests, add a `notes/to-do.md` entry under the test section.

Small `fix` / `patch` follow-ups after a large `feat` are normal and expected; do not try to anticipate everything upfront.

## Working tree reality

The tree often holds hunks from several tasks at once. That is fine — deployment only runs from a clean tree, so intermediate states do not matter. The job is to identify the hunks that form one complete unit and stage only those.

## Cross-references

- `notes/agents.md` rule #3 — the "no commits without explicit instruction" rule
- `notes/agents.md` personality section — semicolons or regular dashes (never em-dashes), American English, brief over verbose
