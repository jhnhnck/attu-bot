---
name: comment-style
description: AttuBot python comment conventions - case, punctuation, brevity, section dividers, todo tags, and noqa reasons. trigger when editing or creating any `.py` file under `attubot/`, `tests/python/`, or `scripts/`; when writing inline or block comments in python; when adding `# noqa`, `# TODO`, `# NOTE`, or `# FIXME` tags; when adding or reviewing module-level section dividers; when answering questions about python comment formatting in this repo.
---

# comment-style

Authoritative reference when writing python comments in this repo. This skill is canonical; update it directly.

## default: write no comment

Only write a comment when the *why* is non-obvious. If removing the line would not confuse a future reader, do not write it. Do not restate what well-named identifiers already say. Do not write "added for issue #X" or "used by Y" - those rot.

## hard rules

- **all lowercase** including the start of sentences. exception: when lowercasing creates ambiguity (proper nouns, acronyms)
- **no trailing period** on single-line comments; periods only when multiple sentences make them necessary
- **one space after `#`** always
- **brief**. if a comment needs paragraphs, the code probably needs restructuring
- comment the *why*, not the *what*

## inline vs block

inline: same line as code, **two spaces** before the `#`, short.
```python
elapsed_days = int(time_diff_sec / SECONDS_PER_DAY)  # floor div keeps tz-safe
```

block: above the line(s), same indent. one blank line before a block that starts a new logical section; no blank line between the comment and the code it describes.
```python
# check if already passed trigger time
if date.today().weekday() == 4 and datetime.now().astimezone() >= friday_rollover:
    friday += timedelta(days=7)
```

if an inline comment needs a full sentence, promote it to a block comment instead.

## examples - good vs bad

```python
# good
x = x + 1  # compensate for boundary

# bad - capitalized
# Check if we already passed trigger time

# bad - trailing period
# handles the paused case.

# bad - restates the code
count = count + 1  # add 1 to count
```

## section dividers

**module level only** - never inside functions or classes.

format: `# --- <label> ---`

```python
# --- initialization ---

logger = get_logger(__name__)

# --- utilities ---


def some_function(): ...
```

avoid `# ======`, `# ####`, or bare `# ---` without a label.

## todo / note / fixme tags

use sparingly. format: all-caps tag, colon, space, lowercase message. only `TODO`, `NOTE`, `FIXME` - no `HACK`, `XXX`, or other variants.

```python
# TODO: move this to the guild object
# NOTE: api keys stored in .toml file; not in db
# FIXME: this breaks on paused epochs
```

## noqa requires a reason

rule #4 from `agents.md`: every `noqa` must include a valid reason. format:

```python
something()  # noqa: PLW0603 - lazy singleton initialization requires global
```

`# noqa` or `# noqa: CODE` with no reason is rejected. the reason must explain *why* the rule is being suppressed for this case, not just restate the rule name.

## what not to write

- no commented-out code in production files - use `wip/` for scratch work
- no redundant file-header comments (the module docstring handles that)
- no decorative ascii-art dividers
- no "what the code does" comments
- no references to issue numbers, PRs, or "the X flow" - those rot

## cross-references

- `notes/agents.md` rule #4 - the noqa-reason rule
- `notes/agents.md` personality section - lowercase comments, semicolons or regular dashes (never em-dashes), american english
