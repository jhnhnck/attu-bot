# style & wording guide

a portable guide for writing clear, consistent notes and to-do lists

---

## general writing principles

- **all lowercase** for body text, notes, annotations, and labels
  - exceptions: proper nouns, in-universe terms, acronyms with established conventions
- **American English** spelling and grammar
- prefer **brief statements** over long explanations
- write the *why*, not the *what* - readers can see what; explain the reasoning
- **active voice, present tense** by default

---

## punctuation

- **no terminal period** on single-sentence items, labels, or short notes
- use a period only when a note has multiple sentences
- no exclamation marks unless genuine excitement warrants it
- no ellipses for trailing thoughts - cut the thought instead
- **semicolons** join two independent clauses or a cause and its consequence
  - e.g. `migration failed; refusing to continue`
- **dashes** ( - ) for trailing asides, parentheticals, or annotations
  - e.g. `deadline moved to friday - check with team`
- no em-dashes; use a regular hyphen-dash ( - )
- no extraneous punctuation at line ends

---

## tags and flags

format inline flags as: `TAG: message` - all-caps tag, colon, space, lowercase message.

common tags:
- `TODO:` - action still needed
- `NOTE:` - clarifying context or caveat
- `FIXME:` - known issue that needs attention

use sparingly. no other variations.

---

## change/mutation notes

when recording that something changed, show before and after:
```
old=weekly new=daily
old=alice,bob new=alice,carol,dave
```

when recording counts or load events:
```
loaded [12] items
processed [4] records
```

---

## error and status notes

- errors start with `Failed:` followed by the specific reason in lowercase
  - include the constraint violated, not just "an error occurred"
  - include actionable suggestions when relevant
  - e.g. `Failed: date must be in the future`
- success notes confirm **what changed**, not just "ok" or "done"
  - for mutations: show before/after
  - for trivial completions: `Done.` is fine

---

## document change descriptions

when logging changes to a document or file, use the format:
```
type(scope): description
```

**types:**
- `fix` - correcting something wrong
- `patch` - minor tweak (wording, small tuning, typo)
- `add` - new content; also used for removals with negative framing
- `chore` - housekeeping (formatting, reorganizing)
- `refactor` - restructuring without changing meaning

**rules:**
- all lowercase, no body text needed for most changes
- description is a noun phrase or casual statement - not imperative verbs
  - good: `fix(budget): wrong tax rate for Q3`
  - bad: `fix(budget): correct the tax rate for Q3`
- pick the most relevant scope; don't list multiple
- describe **what changed**, not how you changed it
