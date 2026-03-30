# commit style

## message format

conventional commits - `type(scope): description`, all lowercase, no body.

**types**: `feat`, `fix`, `patch`, `refactor`, `chore`, `test`
- `fix` - actual bug
- `patch` - minor tweak that isn't a bug (wording, small tuning, typo)
- `feat` - addition; also used for removals and intentional behavior changes with negative/ironic framing
- `chore` - linting, formatting, housekeeping; always isolated from other work

**scope**: the most relevant one when multiple are touched - pick the primary, don't list them.

**description**: plain noun phrases or casual statements. describe what changed, not what was done to achieve it. no formal imperative verbs ("implement", "introduce", "centralize"). personality and humor where it fits naturally - don't force it.

```
fix(hatch): enable one week early; i'm impatient :tieteran:   ← honest why via semicolon
chore: oops all linting fixes                                  ← owns the mistake
fix(wiki): lookup buttons don't die on restart                 ← the bug, not the fix
fix(modlog): bot users were ignored in kick/ban messages       ← same
feat(hatch): trading and collection info                       ← noun phrase, not "implement trading"
patch(hatch): fix up responses and progress message length     ← minor tweak
feat(hatch): less aggressive trade timeout                     ← ironic feat for a behavior change
feat(hatch): no more screaming snakes                          ← negative framing for a removal
```

---

## making a commit

the working tree will often have changes from multiple tasks in progress at once. that's fine - deployment only happens from a clean tree, so intermediate states don't matter. the job is to pick out the hunks that belong together and commit them as one complete unit.

**what makes a unit complete** depends on what it is:

- **feat** - implementation + tests + notes/docs + config/assets, all in one. it's done when the thing it describes is actually done, not when the code compiles.
- **fix / patch** - the change itself plus any test that covers it. if making it work right required touching the db layer or a script, that goes in too.
- **refactor** - every file that references the thing being changed, swept in one commit. no partial refactors left dangling.
- **data or config change** - minimal: just the value and its docs. nothing else.
- **chore** - linting and formatting never ride along with other work. collect them separately.
- **tests** - can go in with the feature they cover, or as a standalone commit filling coverage later. both are fine. if no tests are included, a to-do entry should be added in the test section,

after a large feature commit, small `fix` or `patch` commits for issues that surface in use are normal and expected - don't try to anticipate everything upfront.
