# development process

The shape of work in this repo. One of these loops runs against every plan in `notes/plans/`. Replaces the older "programmer → qa → manager updates plan → repeat" loop, which stalled on bugs near the end of every project.

The skills referenced below are generic and live in `~/.claude/skills/` — they apply to any project, not just this one.

---

## plan shape

Plans live in `notes/plans/<project>.md`. Each plan has:

1. **goals** — small, co-equal, measurable.
2. **pre-mortem** — adversarial pass on the plan before phase 1, via the `pre-mortem` skill. output: revisions to phase order, identified high-risk phases, the walking-skeleton phase 0.
3. **phase 0 — walking skeleton.** thinnest possible end-to-end slice that exercises every layer the project will eventually touch. empty implementations are fine. this pulls integration bugs from month 3 to week 1.
4. **phases 1..n — risk-first, not dependency-first.** order phases by uncertainty, not by build order. the scariest unknown goes first. downstream phases get refactored after each retro.
5. **bug log** — a section in the plan, separate from the phase list. anything qa or the programmer finds that's outside the current phase's scope goes here. never sneaks into the next phase's scope without `bug-triage`.

---

## the phase loop

Each phase repeats this five-step cycle:

1. **plan the phase** — single focused unit with an explicit definition-of-done that names a cross-phase check, not just a per-phase spec ("demo fixture renders end-to-end with zero edge-card overlaps", not just "feature x works").
2. **programmer** — implement the phase. anything found outside scope: into the bug log, not the code.
3. **integration check** — via the `integration-check` skill. different mindset from per-phase qa: verifies the *whole product* still works against fixtures, perf budgets, visual goldens. distinct from `feature-completion` (mechanical phase checklist) and `code-review` (qualitative pass).
4. **phase retro** — via the `phase-retro` skill. three questions: what landed vs spec, what surprised us, what's the residual debt. output feeds the next two steps.
5. **bug triage + plan revise** — `bug-triage` walks the bug log and produces a triaged list with severity and disposition. `plan-revise` takes the retro + triage and updates downstream phases. if a phase's premise no longer holds, rewrite or delete it.

---

## ship gate

Before declaring a project done, run `ship-readiness`. it walks the bug log, classifies each remaining item as blocker or follow-up, produces an explicit cut-line, and emits a deferred-bug list for the next project. "we have bugs left" is normal. "we don't know which ones block ship" is the failure mode this catches.

---

## skill cheat sheet

| step | skill | location |
|---|---|---|
| plan-time pre-mortem | `pre-mortem` | shared |
| per-phase mechanical checklist | `feature-completion` | project |
| per-phase qualitative review | `code-review` | project |
| per-phase whole-product check | `integration-check` | shared |
| between-phase retro | `phase-retro` | shared |
| bug log management | `bug-triage` | shared |
| update plan after retro/triage | `plan-revise` | shared |
| end-of-project gate | `ship-readiness` | shared |
| commit message format | `commit-style` | project (generic version in shared) |
| working tree → commits | `commit-split` | project (generic version in shared) |
| comment conventions | `comment-style` | project |
| file headers | `file-header` | project |

---

## minimum viable adoption

if a plan is small (one or two phases) the full loop is overkill. the floor is:

- write a one-paragraph pre-mortem inline in the plan
- bug log section, even if it stays empty
- run `feature-completion` + a brief integration check at phase end
- run `ship-readiness` before declaring done

larger plans (three+ phases, especially anything with cross-phase dependencies or perf budgets) get the full loop.

---

## generating the project-specific skills

The shared skills (`pre-mortem`, `phase-retro`, `bug-triage`, `integration-check`, `plan-revise`, `ship-readiness`) work in any project. The skills below are project-specific - each one needs to be derived from this project's actual conventions, log, and architecture. The prompts here are short briefs you can paste into Claude inside a new project to generate that skill at `.claude/skills/<name>/SKILL.md`.

### commit-style

> Read the last 100 commits (`git log --oneline -100`) and identify the project's commit conventions: format, types, scope vocabulary, voice/personality, any deliberate quirks (ironic types, self-deprecation, etc.). Write `.claude/skills/commit-style/SKILL.md` extending the generic `~/.claude/skills/commit-style/` (don't restate it). Add: the project's actual scope vocabulary, 5-10 example commits from the log that illustrate the project's voice, and any project-specific rules from the project's style doc if one exists.

### commit-split

> Inspect the project's recent merge / branch history and identify files that typically span multiple logical units in a single working tree (top-level shells, shared registries / command tables, cross-cutting docs, type-augmentation files, top-level config). Write `.claude/skills/commit-split/SKILL.md` extending the generic `~/.claude/skills/commit-split/`. Add: the project-specific multi-commit-files list with one-line reasons each, the project's verify command, and any project-specific staging gotchas. Don't restate the snapshot-and-revert technique - reference it.

### comment-style

> Read 10-20 representative source files across the project's main languages. Identify dominant conventions: case (lowercase vs sentence-case), trailing punctuation, section divider style, TODO/NOTE/FIXME tag format, suppression-marker rules (`noqa`, `eslint-disable`, `@ts-expect-error`, etc.), dash conventions, american vs british spelling. Write `.claude/skills/comment-style/SKILL.md` covering: hard rules, inline vs block, good vs bad examples per language, section dividers, todo tags, and suppression markers. Cite the project's style doc if one exists.

### file-header

> Read 5-10 source files per language in the project. Identify: license header style (SPDX tag, full text, or none), any structured docstring/breadcrumb on top of files, copyright lines, and which file types do/don't get a header. Write `.claude/skills/file-header/SKILL.md` describing per-language conventions and the list of file types that require a header.

### feature-completion

> Read the project's CI config, package scripts (or equivalent), test layout, and any "definition of done" doc. Identify: verify command(s) (test, lint, typecheck, build), test categories (unit / component / e2e / integration), where docs live, where config goes, and any domain rules that need a sanity check (schema migrations, security gates, etc.). Write `.claude/skills/feature-completion/SKILL.md` as a literal yes/no checklist with sections: tests, documentation, configuration, linting, domain sanity check, final gate. Add a "scope" section delineating it from the shared sibling skills (`integration-check`, `phase-retro`, `ship-readiness`).

### code-review

> Read the project's main architecture doc, the last ~30 fix commits, and identify: high-volume past bug patterns, security threat model, language/stack quirks (`exactOptionalPropertyTypes`, GIL, lifetimes, async sequencing, etc.), and cross-module gotchas. Write `.claude/skills/code-review/SKILL.md` as a multi-pass review (correctness, design, repo-specific bug patterns, tests, documentation, security, style). Each pass defers to existing style skills (`commit-style`, `comment-style`, `file-header`, ...) rather than restating their rules. Cross-reference the shared sibling skills (`integration-check`, `bug-triage`, `phase-retro`, `ship-readiness`).


