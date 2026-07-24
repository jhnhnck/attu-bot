# nova-w2 log

## starting phase 0 — 2026-07-24

- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/nova-w2
- branch: phase/nova-w2
- parent branch: trunk
- confirmed DoD:
  - `python -c 'from nova_core.manifest import FeatureManifest; m = FeatureManifest(name="x"); print(m.tasks)'` exits 0 printing `[]`
  - `bot.listen()` programmatic pattern confirmed in unit test; fallback to `bot.add_listener()` if needed (noted in commit)
  - `grep -n 'FeatureContext\|load_base\|load_all' nova_core/client/events.py` shows all three calls inside `_do_ready_init()` after `await init_database(...)`
  - `test_feature_loader.py` passes: task wired, event handler registered, setup fn called, unknown feature logs warning, missing manifest attr logs warning
  - `docker compose run tests` passes
  - cross-phase check: no circular imports; `nova_core.manifest` and `nova_core.loader` do not import from feature packages
