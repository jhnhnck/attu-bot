# tasks.md - Background Task Scheduler

How the `TaskScheduler` and `BaseTask` system works, and how to use them.

---

## Overview

`attubot/tasks/scheduler.py` exports a module-level singleton `scheduler` of type `TaskScheduler`. It manages two categories of work:

| Category | API | How it runs |
|---|---|---|
| Recurring task | `scheduler.register(task)` then `scheduler.start_all()` | Loop driven by `_run_loop()`; restarts automatically after each tick |
| Fire-and-forget job | `scheduler.add_job(coro, kind, *parts)` | Runs once in the background; no restart |

---

## Recurring Tasks - BaseTask

All recurring tasks extend `BaseTask` (`attubot/tasks/base.py`). Key class attributes:

| Attribute | Type | Purpose |
|---|---|---|
| `name` | `str` | Identifier used in logs and `TaskLoop[name]` wrapper |
| `interval` | `timedelta \| None` | Fixed sleep between ticks; set to `None` for dynamic scheduling |
| `run_immediately` | `bool` | If `True`, `run()` is called once right after `on_start()` before the first sleep |
| `run_once` | `bool` | If `True`, `run()` is called exactly once then the task stops; works with or without `run_immediately` |

Lifecycle methods called by the scheduler - override as needed:

| Method | When called |
|---|---|
| `on_start()` | Once, before entering the run loop |
| `run()` | Every tick (required - abstract) |
| `next_run()` | If `interval is None`; return the `datetime` for the next tick |
| `on_stop()` | Once, after the loop exits |
| `request_wake()` | Call from outside the task to interrupt a dynamic sleep; causes `next_run()` to be re-evaluated immediately. no-op if the task is not currently sleeping |

### Fixed interval example

```python
class ErrorHookTask(BaseTask):
    name: str = 'ErrorHook'
    interval: timedelta | None = timedelta(hours=1)

    async def run(self) -> None: ...  # called every hour
```

### Dynamic scheduling example

```python
class DatabaseBackupTask(BaseTask):
    name: str = 'DatabaseBackup'
    interval: timedelta | None = None  # use next_run() instead

    async def next_run(self) -> datetime | None:
        # return datetime of next backup window
        return next_backup_time()

    async def run(self) -> None: ...
```

### run-once example

use `run_once = True` for tasks that need lifecycle hooks (`on_start`, `on_stop`, error reporting) but should only execute `run()` a single time. pair with `run_immediately = True` to run on the first tick without waiting for the interval:

```python
class ChatInitTask(BaseTask):
    name: str = 'ChatInit'
    interval: timedelta | None = timedelta(hours=1)
    run_immediately: bool = True
    run_once: bool = True

    async def on_start(self) -> None: ...  # await dependencies
    async def run(self) -> None: ...        # called once, then task exits
    async def on_stop(self) -> None: ...   # cleanup
```

with `run_immediately = False`, the task sleeps one interval first, then calls `run()` once and stops.

### Registering a task

bot tasks are instantiated as module-level singletons and added to the bot's scheduler via `register_bot_tasks()` in `attubot/tasks/__init__.py`:

```python
from attubot.tasks.my_feature import MyFeatureTask

my_feature_task = MyFeatureTask()

def register_bot_tasks(s):
    ...
    s.register(my_feature_task)
```

the bot calls `register_bot_tasks(scheduler)` from `attubot/client/events.py` right before `scheduler.start_all()` on `on_ready`. registration is intentionally not done at module-import time; the ingestor process imports the same package and would otherwise inherit (and start) every bot task, racing with the bot for shared db state like reload signals.

the ingestor registers its own task set explicitly in `attubot/ingestor/__init__.py` and does not call `register_bot_tasks()`.

---

## Fire-and-Forget Jobs - add_job

Use `scheduler.add_job()` to kick off a one-shot coroutine in the background without blocking the caller.

```python
scheduler.add_job(coro, kind, *parts)
```

| Parameter | Type | Purpose |
|---|---|---|
| `coro` | `Coroutine` | the awaitable to run |
| `kind` | `str` | CamelCase task kind (see naming scheme below) |
| `*parts` | `object` | optional context values coerced to str and joined with `:` |

The scheduler builds the task name: `Kind[part1:part2:...]` (or just `Kind` if no parts).

Errors are caught, logged, and forwarded to the error webhook automatically.

---

## Task Naming Scheme

All task names use the format `Kind[context:parts]` or plain `Kind` when there is no context.

| Kind | Used for | Example |
|---|---|---|
| `Job` | maintenance/repair operation from a slash command | `Job[fix_starboard_recount]` |
| `Job` | with channel/user context | `Job[fix_messages:#general]`, `Job[fix_author_names:9876543210]` |
| `NovaYearEvent` | year-rollover triggered by `NovaYearTask` | `NovaYearEvent[GuildConfig(id=...)]` |
| `ManualYearAdvance` | admin-forced year override | `ManualYearAdvance[123456789]` |
| `HatchAnimation` | egg hatch UI animation | `HatchAnimation[abc123def456]` |
| `PongTask` | debug pong response | `PongTask[username]` |
| `PresenceUpdate` | out-of-cycle presence refresh | `PresenceUpdate[immediate]`, `PresenceUpdate[hatch_day]` |
| `LogoUpdate` | out-of-cycle logo refresh | `LogoUpdate[immediate]` |

For out-of-cycle triggers of a named recurring task, use the `BaseTask.name` as the kind with a context part describing the trigger reason (e.g. `immediate`, `hatch_day`).

Recurring task loops are automatically wrapped as `TaskLoop[task.name]` by the scheduler - do not manually construct these names.

---

## Circular Import Note

Tasks that call `scheduler.add_job()` on themselves or other tasks must use local imports to avoid circular dependency with `tasks/__init__.py`:

```python
async def run(self) -> None:
    ...
    from attubot.tasks.presence import presence_update_task
    from attubot.tasks.scheduler import scheduler  # local import avoids circular dep

    scheduler.add_job(presence_update_task.run(), 'PresenceUpdate', 'immediate')
```

Command files (`attubot/commands/`) can import `scheduler` at the top of the module without issue.

---

## How to Add a New Recurring Task

1. Create `attubot/tasks/my_feature.py` with the standard file header
2. Define a class extending `BaseTask`; set `name`, `interval` (or `None`), and optionally `run_immediately`
3. Implement `run()` (required); implement `on_start()` if you need to wait on config or the bot being ready
4. Implement `next_run()` if `interval is None`
5. Add a module-level singleton: `my_feature_task = MyFeatureTask()`
6. In `attubot/tasks/__init__.py`, import the singleton and add `s.register(my_feature_task)` inside `register_bot_tasks()`
7. Add a row to the tasks table in `notes/agents.md`

## How to Fire a One-Shot Job from a Command

1. Import `scheduler` at the top of the command module: `from attubot.tasks import scheduler`
2. Call `scheduler.add_job(my_coro(...), 'Job', 'operation_name')` after responding to the user
3. If additional context is needed (channel, user, guild), add it as extra parts: `scheduler.add_job(coro, 'Job', 'fix_messages', f'#{channel.name}')`
4. Use the `Job` kind for maintenance operations; use the task's `BaseTask.name` as kind for out-of-cycle task triggers

---

## metadata

```yaml
last_updated: 13 April 2026
```
