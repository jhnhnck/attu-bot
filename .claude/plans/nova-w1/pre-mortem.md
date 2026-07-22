# pre-mortem — nova-w1: structural prerequisites

**Bottom line:** proceed with revisions — three issues require plan edits before phase 1 starts; none invalidate the phase order. changes are surgical.

---

### risks

- [high] integration — phase 0 walking skeleton creates a circular import: `nova_core/__init__.py` re-exports from `doom_bot.client`; making `doom_bot/__init__.py` a shim that does `from nova_core import *` causes python to hit nova_core during doom_bot package init, but nova_core is still mid-load so the re-export returns a partially-initialized module; `start_bot_loop` and other late-defined names will be absent · probe: redesign phase 0 — nova_core/__init__.py contains ONLY standalone metadata constants (no imports from doom_bot); doom_bot/__init__.py is NOT shimmed in phase 0; doom-bot.py imports from doom_bot for now and also does `import nova_core` to prove the package is on the path; circular import risk is eliminated entirely

- [high] premise — `config.bridge` does not exist on `NovaConfig`; `config.bridge.bind_host`, `config.bridge.bot_port`, `config.bridge.secret`, `config.bridge.replay_window` are referenced in `bridge/router.py` and `bridge/hmac.py` but the bot's config.py has no `bridge` attribute; the bridge crashes with AttributeError at the first `start_bridge_task()` call (on_ready); phases 0-2 claim "bot runnable" without verifying whether this crash is fatal to the process or swallowed · probe: before phase 1 starts, read `client/events.py` near line 204 to confirm `_do_ready_init()` runs `start_bridge_task()` inside a try/except that swallows the error; if it does not, "bot runnable" for phases 0-2 is false and bridge bug fixes must move to phase 1

- [medium] scope — `config.primary_guild` has 12 confirmed call sites across markers.py, years.py, calendar.py, commands/trees.py, tasks/logo_update.py, and config.py; `config.secondary_server` has 1 (commands/fix.py); `NovaConfigRepr` TypedDict also declares `primary_guild: int`; the plan says "update all call sites" without enumerating them; phase 4 must start with a grep to establish the complete list before touching any code · probe: run `grep -rn 'config\.primary_guild\|config\.secondary_server\|primary_guild\b' apps/` at phase 4 start; count must match what was found in pre-mortem; any surprise hits are scope additions

- [medium] scope — Dockerfile's git-info stage has a `sed` command that stamps version into `apps/bot/doom_bot/__init__.py`; after phase 1, the target path is `apps/bot/nova_core/__init__.py`; if the sed path is wrong, the docker build stamps the wrong file and version info is lost silently; ruff check and basedpyright will not catch this because it's a shell sed command, not a python import · probe: add "Dockerfile sed path updated to nova_core/__init__.py" as an explicit DoD item for phase 1; grep Dockerfile for `doom_bot/__init__.py` before calling phase 1 done

- [medium] integration — `attu_logging.configure()` is called at bot startup before `config.on_load()`; `config.error_hook` (the webhook URL) is only populated in `on_load()` after DB connect; the plan calls `attu_logging.configure(webhook_url=config.error_hook)` in doom-bot.py but `config.error_hook` is None at that point; the contract's `configure()` signature stores webhook_url module-level but can only be called once (idempotent guard); a second call after on_load() would silently skip setting the URL · probe: redesign the phase 2 interface as two separate callpoints: `attu_logging.configure()` at startup (structlog setup only, no webhook_url param); `attu_logging.set_webhook_url(config.error_hook)` called inside `on_load()` after the DB stage; the module-level `_webhook_url` variable is set by `set_webhook_url()` not by `configure()`; webhook.py reads `_webhook_url` lazily at call time

- [medium] expertise — after phase 2 migration, `DEBUG=1` env var no longer lowers the root logger level; `attu_logging/config.py`'s `_resolve_root_level()` reads `LOG_LEVEL` only, not `DEBUG`; the old `doom_bot/logging.py` read `DEBUG` to set root level to TRACE (5); developers using `DEBUG=1` to enable debug output will get INFO-level output after phase 2 with no error or warning · probe: in phase 2, pass `level='DEBUG' if 'DEBUG' in environ else None` to `attu_logging.configure()` from doom-bot.py; or document in phase 2's commit that `DEBUG=1` is replaced by `LOG_LEVEL=DEBUG`; either way, call it out explicitly in the commit message

- [low] expertise — phase 1 DoD grep checks `--include="*.py"` only; Dockerfile has three doom_bot path references (sed target, COPY source, __init__.py stamp copy); docker-compose files have `doom-bot` name references; shell scripts have path references; none of these are caught by ruff or python grep · probe: extend phase 1 DoD grep to cover `Dockerfile*`, `*.yml`, `*.sh` with `grep -rn doom_bot . --exclude-dir=.venv --exclude-dir=.claude` before declaring done

- [low] scope — phase 2 inlines `break_at_newline` into `attu_logging/webhook.py`; this function also lives in `nova_core/client/util.py` and is used by other callers; the inline copy must match the original byte-for-byte OR the two diverge silently; the plan doesn't call this out · probe: add DoD item for phase 2: "inlined break_at_newline matches nova_core/client/util.py implementation (diff confirms zero delta)"

---

### walking-skeleton check

phase 0 as drafted is broken: the doom_bot/__init__.py shim causes circular imports (see high integration risk above). revised phase 0 proposal:

- create `apps/bot/nova_core/__init__.py` with ONLY standalone metadata constants (copy __title__, __version__, __schema__, etc. from doom_bot/__init__.py; add no imports)
- update `pyproject.toml`: add nova_core to ruff isort `known-first-party`, basedpyright `extraPaths`, pytest `pythonpath` (apps/bot already there so nova_core is auto-discovered), `coverage.run.source`
- update `apps/bot/Dockerfile`: all three doom_bot path references → nova_core (sed target, COPY source, stamp copy path)
- doom_bot/__init__.py is NOT touched; doom-bot.py is NOT changed
- DoD: `python -c "import nova_core; print(nova_core.__version__)"` exits 0; doom-bot.py still runs via doom_bot; ruff passes on nova_core/__init__.py

this retires the "tooling accepts nova_core as a package" unknown without any shim complexity or circular import risk. phase 1 does the actual flip.

---

### phase-order revisions

| original | proposed | reason |
|---|---|---|
| 0. walking skeleton (shim design) | 0. walking skeleton (standalone metadata only; no shim) | eliminates circular import risk; phase 0 still retires the "tooling accepts nova_core" unknown |
| 1. full package rename | no change | highest blast-radius, must go first; correct order |
| 2. attu_logging migration | no change | can only proceed cleanly after doom_bot is deleted |
| 3. bridge bug fixes | no change | bridge is currently broken (no config.bridge on NovaConfig); fix before phase 4 config restructure |
| 4. config restructure + string cleanup | no change | last because it touches the widest operational surface; all other code is stable by then |

---

### definition-of-done additions

- phase 0 — add: `python -c "import nova_core; print(nova_core.__version__)"` exits 0 with the expected version string; Dockerfile sed path references nova_core/__init__.py; no doom_bot/__init__.py changes present in the commit
- phase 1 — add: grep over Dockerfile, docker-compose files, and shell scripts for doom_bot confirms zero hits (not just *.py); `__version__` and `__build_time__` stamping in git-info stage uses nova_core path; explicit note that bot is runnable but bridge is excluded (config.bridge not yet defined)
- phase 2 — add: `attu_logging.set_webhook_url()` exists and is called from on_load(); inlined break_at_newline matches nova_core/client/util.py; explicit note in commit that DEBUG=1 is superseded by LOG_LEVEL=DEBUG for root logger level
- phase 3 — add: confirm start_bridge_task() error handling before writing code (probe outcome documented in commit); bot runnable with bridge now included (config.bridge exists after this phase)
- phase 4 — add: pre-step grep for `config.primary_guild`, `config.secondary_server`, `NovaConfigRepr` confirms full call-site list before any edits; SystemConfigDocument.primary_guild field in attu_models noted as orphaned (not a code bug; WS3 scope to remove)
