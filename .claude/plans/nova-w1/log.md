# log — nova-w1: structural prerequisites
(append per-phase entries here; chronological)

## starting phase 0 - 2026-07-23

- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/nova-w1
- branch: phase/nova-w1
- parent branch: trunk
- dod: `python -c "import nova_core; print(nova_core.__version__)"` exits 0; Dockerfile sed target references `nova_core/__init__.py`; ruff/basedpyright/coverage list `nova_core`; `doom_bot/__init__.py` unchanged; bot runnable via doom_bot (bridge excluded)

## phase 0 retro - 2026-07-23

**what landed vs spec**
- `nova_core/__init__.py` created with all 10 metadata constants; zero doom_bot imports; DoD check passes
- `nova_core.__version__` resolves to `80.0-dev` live in container (base file: `80.0`; git-info stage appends `-{commit}` at build time; confirmed by integration-check)
- doom_bot unchanged; bot entrypoint unaffected; 180 component tests passed with no new failures
- ruff `known-first-party` and coverage `source` updated in root `pyproject.toml`; basedpyright and pytest required no change (apps/bot already in extraPaths/pythonpath respectively, nova_core auto-discovered by both)
- Dockerfile: nova_core COPY and stamp lines added alongside existing doom_bot lines (additive; doom_bot lines remain intact for phase 0 constraint)

**what surprised us**
- basedpyright auto-discovery confirmed in practice; the scope anticipated no pyproject change was needed, and implementation verified it
- Dockerfile took the additive path (nova_core lines added, doom_bot lines untouched) rather than replacing doom_bot references; this satisfies the phase 0 constraint that doom_bot must remain runnable, but it means phase 1 must explicitly remove the now-redundant doom_bot COPY and stamp lines when doom_bot is deleted

**what residual debt remains**
- pre-existing em-dashes in plan.md and log.md; documentation files only; classified in bug-triage below

## revision after phase 0 - 2026-07-23

phase 1 revised: added explicit Dockerfile cleanup step to scope (remove doom_bot COPY and git-info stamp lines left by phase 0 additive approach); the DoD grep already requires this, but the scope was silent and an implementer could miss three distinct Dockerfile lines that need removal.

phases 2-4: valid - no scope changes needed; their premises assume nova_core in its phase-1 moved state, which is sequencing, not a phase-0 finding.
