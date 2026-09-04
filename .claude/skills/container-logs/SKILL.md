---
name: container-logs
description: practical reference for reading AttuBot container logs - which compose file, where the structlog pipeline puts what, how to strip the console renderer's ANSI for grep work, how to parse the json renderer with jq, and how to filter non-structlog noise. trigger when the user asks to "check logs", "tail logs", "what is core logging", "what did the bot log", "find this error in logs", "parse logs", or anything mentioning `docker compose logs`, `journalctl`, structlog output, ANSI stripping, jq on log output, or container output for AttuBot's prod or dev stacks. when the user does not specify, assume **prod**.
---

# container-logs

reading logs from the AttuBot containers with `docker compose logs`. assume **prod** unless the user says otherwise.

## paths and services

| stack | working dir | compose file | containers (service → name) |
|---|---|---|---|
| **prod** (default) | `/srv/services/doom-bot` | `docker-compose.prod.yml` | `core` → `doom-bot-core-1`, `server` → `doom-bot-server-1`, `ferret`, `postgres` |
| **dev** | `/home/jhn/Projects/doom-bot` | `docker-compose.dev.yml` | data-plane only (`ferret`, `postgres`, `mongo`); no bot service; `tests` is one-shot (`attu-dev-tests`) |

there is no committed `docker-compose.yml`, so always pass the file: `docker compose -f /srv/services/doom-bot/docker-compose.prod.yml logs`.

prod services use `logging: driver: journald`, so logs also live in the host journal — `journalctl CONTAINER_NAME=doom-bot-core-1 ...` is an alternative to `docker compose logs` when you need richer time-range or persistence beyond what docker keeps. the docker frontend reads from journald either way.

> **never `exec` into a prod container** to dump env, run shells, or anything else without explicit user authorization. log reads via `docker compose logs` or `journalctl` are passive and fine.

## docker compose logs - the flags that actually matter

```bash
docker compose logs core              # all retained logs for one service
docker compose logs --tail 200 core   # last 200 lines
docker compose logs -f core           # follow (run in background; do not poll)
docker compose logs --since 10m core  # last 10 minutes (or `--since 2026-05-09T12:00`)
docker compose logs --until 2h core   # up to 2h ago
docker compose logs --timestamps core # docker-side timestamps (separate from any in the payload)
docker compose logs --no-log-prefix   # strip the `core-1  | ` per-line prefix
docker compose logs --no-color        # strip *docker's* coloring; does NOT strip structlog ANSI
```

multi-service: `docker compose logs core server`. omit a service name to get all.

> `-f` against prod is fine; if you `run_in_background: true` the Bash call, you'll be notified on output. do not poll with `sleep` loops.

## the two render shapes

`packages/attu-logging/attu_logging/config.py` selects the renderer from `LOG_FORMAT`:

- `LOG_FORMAT` unset or `console` → `structlog.dev.ConsoleRenderer(colors=True, force_colors=True)` ← **prod default today**
- `LOG_FORMAT=json` → `structlog.processors.JSONRenderer` + iso `TimeStamper`

both shapes carry the same fields (level, event, logger, contextvars, kwargs). only the wire format differs. `force_colors=True` means console output emits ANSI even when stdout is a pipe — that is why `--no-color` does not silence it.

### console shape

after `--no-log-prefix` and ANSI-stripping, one record looks like:

```
[debug    ] GET https://discord.com/api/v10/... has returned 200 [discord.http]
[info     ] changing icon rotation from 134.13 to 134.25 [nova_core.tasks.logo_update]
[warning  ] slow task: LogoUpdateEvent took 5151ms [nova_core.tasks.scheduler]
```

structure: `[<level padded to 9 chars>] <event message>     <key>=<value> ... [<logger.name>]`

bound contextvars (e.g. `command=`, `user_id=`, `guild_id=`, `channel_id=` from `client/events.py` and `client/modlog.py`) and per-call kwargs render as `key=value` pairs between the message and the trailing `[logger]`.

multi-line records (tracebacks via `format_exc_info`) span many physical lines — only the first carries the `[level    ]` opener.

### json shape

```json
{"event":"slow task: LogoUpdateEvent took 5151ms","logger":"nova_core.tasks.scheduler","level":"warning","timestamp":"2026-05-09T13:42:01.123456Z"}
```

contextvars/kwargs land as top-level keys alongside `event`/`logger`/`level`/`timestamp`. tracebacks come through as `exception` (string).

**enabling json in prod** requires editing `docker-compose.prod.yml` (add `LOG_FORMAT: "json"` under the `core:` and/or `server:` `environment:` block) and `docker compose up -d core`. that is a deploy-shaped change; confirm with the user before doing it. for a one-shot inspection, prefer parsing the console output (recipes below) over flipping the format.

## stripping ANSI from console output

structlog's color codes survive `--no-color`. the universal escape stripper is a single sed:

```bash
sed -E $'s/\x1b\\[[0-9;]*[a-zA-Z]//g'
```

put it after `docker compose logs` and before any grep/awk that cares about visible characters:

```bash
docker compose logs --no-log-prefix --tail 500 core \
  | sed -E $'s/\x1b\\[[0-9;]*[a-zA-Z]//g'
```

(the `$'...'` form is zsh/bash ANSI-C quoting; it lets `\x1b` decode to a real `ESC` byte. plain `'...'` will not work.)

## ignoring "invalid" lines

things in the docker logs stream that are **not** structlog records:

- `core-1  |` per-line prefix → strip with `--no-log-prefix`.
- raw `print(...)` from third-party imports at startup (e.g. pynacl warning, asyncio debug spam) — comes through as plain text, no `[level    ]` bracket.
- traceback continuations — start with whitespace or `Traceback`, not `[`.
- empty lines.

robust filter for a console-mode log to "only structlog lines":

```bash
docker compose logs --no-log-prefix --tail 1000 core \
  | sed -E $'s/\x1b\\[[0-9;]*[a-zA-Z]//g' \
  | grep -E '^\[(trace|alert|debug|info|warning|error|critical) *\] '
```

robust filter for a json-mode log to "only valid json records":

```bash
docker compose logs --no-log-prefix --tail 1000 core \
  | jq -R 'fromjson? // empty'
```

`fromjson?` returns null on non-json input (the `?` swallows the parse error); `// empty` drops the nulls so jq's output is purely the parsed records. this is the canonical pattern for reading a mixed text/json stream with jq.

## jq recipes (when LOG_FORMAT=json is on)

assume the prefix-stripped, json-parsed stream:

```bash
LOGS='docker compose logs --no-log-prefix core | jq -R "fromjson? // empty"'
```

filter by level:
```bash
eval "$LOGS" | jq 'select(.level=="warning" or .level=="error" or .level=="critical")'
```

filter by logger (prefix match, useful for "everything from nova_core.tasks"):
```bash
eval "$LOGS" | jq 'select(.logger | startswith("nova_core.tasks"))'
```

filter by event substring:
```bash
eval "$LOGS" | jq 'select(.event | test("slow task"))'
```

filter by bound contextvar (commands logger binds `user_id`, `guild_id`, `channel_id`, `command`):
```bash
eval "$LOGS" | jq 'select(.guild_id == 1001828025756819456)'
eval "$LOGS" | jq 'select(.command == "stars")'
```

compact one-line table — timestamp, level, logger, event:
```bash
eval "$LOGS" | jq -r '"\(.timestamp) \(.level | ascii_upcase | .[0:4]) \(.logger) :: \(.event)"'
```

group by logger, count records (rough hot-spot sketch):
```bash
eval "$LOGS" | jq -s 'group_by(.logger) | map({logger: .[0].logger, n: length}) | sort_by(-.n)'
```

errors with stack trace, last 50:
```bash
eval "$LOGS" | jq 'select(.level == "error" and .exception) | {timestamp, logger, event, exception}' | tail -n 50
```

## console-mode equivalents (when LOG_FORMAT is unset)

after the sed strip, plain grep/awk works. patterns assume the structure-line filter above is in place.

filter by level:
```bash
... | grep -E '^\[(warning|error|critical) *\]'
```

filter by logger (the trailing `[logger.name]`):
```bash
... | grep -E '\[nova_core\.tasks\.[a-z_]+\]$'
```

filter by event substring (works on the middle of the line):
```bash
... | grep -F 'slow task'
```

extract level + event + logger as columns (awk against the bracket structure):
```bash
... | awk 'match($0, /^\[([a-z]+) *\] (.*) \[([^]]+)\]$/, m) { printf "%-8s %-40s %s\n", m[1], m[3], m[2] }'
```

contextvars are positional `key=value` pairs in the middle of the line; for a single key, prefer:
```bash
... | grep -oE 'guild_id=[0-9]+' | sort -u
```

if you find yourself wanting structured queries against console output, that is the cue to enable `LOG_FORMAT=json` instead of building more sed.

## the discord.http knob

`apps/bot/nova_core/client/__init__.py:_setup_discord_logging` pins the `discord.http` logger to **WARNING when DEBUG is unset**, **DEBUG when DEBUG is set**. so in default prod logs you see only rate-limit warnings from pycord, not per-request traces. set `DEBUG: "1"` on the `core:` env in compose and restart to opt back in.

other noisy loggers pinned to WARNING in `_configure()`: `pymongo`, `aiohttp.access`, `discord.gateway`. they ignore `LOG_LEVEL=DEBUG` unless you change the pin.

## journalctl alternative (prod only)

`docker-compose.prod.yml` sets `logging.driver: journald` for `core` and `server`. when docker's retention has rotated past what you need, the host journal still has it:

```bash
journalctl CONTAINER_NAME=doom-bot-core-1 --since "2 hours ago" -o cat
```

`-o cat` drops journald's own per-line metadata so the output matches `docker compose logs --no-log-prefix`. add `--since`/`--until` with iso timestamps for narrower windows.

## anti-patterns

- piping `docker compose logs` straight into `jq` without `fromjson?` — first non-json line aborts the pipeline.
- assuming `--no-color` removes the ANSI from the structlog payload — it does not. only `sed` (or another ANSI stripper) does.
- relying on a fixed column count from awk on console mode — bound contextvars vary in number per record. anchor on the bracket structure (`^\[...\]` opener, `\[...\]$` closer) rather than counting fields.
- editing `LOG_FORMAT` in prod for a one-off inspection — if you only need one query, parse the console stream. flipping the format is a deploy-shaped action.
