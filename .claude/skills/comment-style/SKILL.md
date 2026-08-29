---
name: comment-style
description: AttuBot python comment conventions. trigger when editing or creating any `.py` file under `apps/`, `packages/`, or `tests/`; when writing inline or block comments in python; when adding `# noqa`, `# TODO`, `# NOTE`, or `# FIXME` tags; when adding or reviewing module-level section dividers; when answering questions about python comment formatting in this repo.
---

# comment-style (AttuBot overlay)

read `~/.claude/skills/comment-style/SKILL.md` once for the universal rules. this skill is canonical for AttuBot; update it directly.

project-specific additions below.

## noqa cross-reference

the noqa-reason requirement is rule #4 in `CLAUDE.md`. format:

```python
something()  # noqa: PLW0603 - lazy singleton initialization requires global
```

## cross-references

- `CLAUDE.md` rule #4 - the noqa-reason rule
- `CLAUDE.md` personality section - lowercase comments, semicolons or regular dashes (never em-dashes), american english
