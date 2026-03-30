# comment style guide

coding convention for inline and block comments in `attubot/`.

---

## general rules

- write comments in **all lowercase**, including the start of sentences
- do not end comments with a period unless the comment contains multiple sentences
- always put **one space** after the `#`
- keep comments brief - prefer a few words over a full sentence where meaning is clear
- comment the *why* not the *what*; avoid restating what the code already says

### examples

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

---

## inline comments

- placed on the same line as the code, after at least **two spaces**
- short; if it needs a full sentence, use a block comment above instead

```python
elapsed_days = int(time_diff_sec / SECONDS_PER_DAY)  # floor div keeps tz-safe
```

---

## block comments

- placed **above** the line(s) they describe, indented to the same level
- one blank line before a block comment that starts a new logical section (not required within a tight block)
- no blank line between a block comment and the code it describes

```python
# check if already passed trigger time
if date.today().weekday() == 4 and datetime.now().astimezone() >= friday_rollover:
    friday += timedelta(days=7)
```

---

## section dividers

use `# ---` style dividers **only** at module level to separate major logical sections of a file. do not use them inside functions or classes.

format: `# --- <label> ---`

```python
# --- initialization ---

logger = get_logger(__name__)

# --- utilities ---


def some_function(): ...
```

avoid decorative styles like `# ======`, `# ####`, or bare `# ---` without a label.

---

## todo / note / fixme tags

use sparingly. format: `# TODO:`, `# NOTE:`, `# FIXME:` (all caps tag, colon, space, lowercase message)

```python
# TODO: move this to the guild object
# NOTE: api keys stored in .toml file; not in db
# FIXME: this breaks on paused epochs
```

do not use other tag variations (`# HACK`, `# XXX`, etc.).

---

## what not to do

- no commented-out code left in production files - use `wip/` for scratch work
- no redundant file-header comments (the module docstring handles that)
- no excessive decoration or ascii-art dividers
