# AttuBot

A Discord bot for the Attu Project that automates in-universe timekeeping, year-transition announcements, wiki management, and related server utilities.

## features

- tracks in-universe time and automates year transitions: announcements, channel name updates, wiki edits
- retrieves year info and links to specific years in lore channels
- starboard and ccboard reaction boards, message backfill, and moderation logging
- egg collection game with rarity-based hatching, trading, and leaderboards
- reminders for in-universe dates
- FamilyEcho family tree links and family tree editor account linking
- admin API (attu_server) for config, feature toggles, and repair operations; talks to the bot over an HMAC-signed bridge

## commands

### users

- **/ping**, **/pong**: checks if the bot is online
- **/version**: current version and container build time
- **/color**: shows the current bot theme color

- **/year**: utilities related to current, past, or future years
  - **/year check [year]**: prints year info (start date, end date, duration); defaults to next year if omitted
  - **/year link \<year\> [channel]**: links to the specified year in a lore channel; defaults to #lore-news
  - **/year search \<year\>**: prints a search query for timelining

- **/wiki**: wiki lookup
  - **/wiki random**: gets a random page from the wiki
  - **/wiki lookup \<query\>**: searches the wiki for relevant pages

- **/remind**: reminders for in-universe (Haracalnde) dates
  - **/remind add**: sets a reminder for a date
  - **/remind list**: views your active reminders
  - **/remind cancel**: cancels an active reminder

- **/egg**: collects an egg
- **/eggs**: egg collection game
  - **/eggs hatch**: hatches your next ready egg
  - **/eggs view**: views your egg collection thread
  - **/eggs give \<user\> [rarity]**: gives one of your eggs to another user
  - **/eggs progress**: views your collection progress by rarity with progress bars
  - **/eggs leaderboard hatched**: top collectors by total hatched
  - **/eggs leaderboard collected**: top collectors by most complete set

- **/stars**: starboard browsing and leaderboards
  - **/stars random**: shows a random message with 2 or more stars
  - **/stars lost**: shows a random message with exactly 1 star
  - **/stars recheck \<message_link\>**: force-updates the starboard post for a specific message
  - **/stars leaderboard most-stars**: top users by total stars received
  - **/stars leaderboard most-starred**: top users by number of messages on the starboard
  - **/stars leaderboard most-given**: top users by total stars given
  - **/stars leaderboard top-messages**: top messages by stars (ccboard only)

- **/link family**: FamilyEcho family trees
  - **/link family list**: lists all registered family trees
  - **/link family view**: gets a temporary FamilyEcho viewer link for a registered family
  - **/link family set**: registers a family tree from an existing message link
  - **/link family upload**: registers a family tree by uploading the file directly

### admin

- **/time**: controls passage of in-universe time (admin only; see [docs/features/timekeeping.md](docs/features/timekeeping.md))
  - **/time advance**: manually advances to the next year, ignoring all checks
  - **/time pause**: pauses the passage of time
  - **/time resume**: resumes the passage of time
  - **/time dilate \<days\>**: adjusts the year length

- **/marker**: manages year marker messages (admin only)
  - **/marker save \<year\> \<link\> [force]**: updates a marker to point to a different message
  - **/marker set \<year\> \<snowflake\>**: sets the marker timestamp for when a specific year starts
  - **/marker clear \<year\> \<channel\>**: removes a marker for a specific channel and year

- **/wiki block \<user\> \<reason\>**: blocks a user from the wiki (admin only)

- **/query**: message searches (admin only)
  - **/query pins \<channel\>**: finds all "pinned a message" system messages in a channel

### admin api

repair and diagnostic operations are no longer slash commands. they live on attu_server's api-key protected `/admin` routes, which call the bot over the bridge:

| area | routes |
|---|---|
| guilds | list guilds, channels, roles; read and patch per-guild config keys; enable or disable features |
| reload | guild, theme, or system reload signals |
| ops | message backfill (channel or guild), ccboard regen/purge/recover/cleanup/recount, logo and emoji-sync and year-links triggers, version/scheduler/year-stats/epoch info, message inspection |

`scripts/nova_admin.py` is an interactive REPL over those routes (`guild`, `config`, `feature`, `reload`, `backfill`, `ccboard`, `trigger`, `info`, `inspect`); `scripts/bridge_curl.py` signs raw bridge calls for manual use.

## setup

### configuration

1. copy `config/sample.env` to `.env` and fill in the postgres credentials (FerretDB runs on postgres until the mongo cutover)
2. copy `config/attu-bot.sample.toml` to `.secrets/attu-bot.toml` and fill in your values (bot token, wiki credentials, authorized guild IDs, etc.); the compose stack mounts both files into each container
3. runtime guild settings (epoch, channels, roles, theme) live in MongoDB and are updated through bot commands or the admin API

compose is split into `docker-compose.prod.yml` (bot, server, database) and `docker-compose.dev.yml` (database, dev seed, tests, standalone `mongo`); there is no default `docker-compose.yml`, so pass `-f` or add a gitignored symlink named `docker-compose.yml` pointing at the one you use

### docker (recommended)

```bash
git clone https://github.com/jhnhnck/attu-bot.git && cd attu-bot
mkdir -p .secrets
cp config/sample.env .env
cp config/attu-bot.sample.toml .secrets/attu-bot.toml
vim .env .secrets/attu-bot.toml
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml logs -f
```

### local development

uv workspace; member packages live under `apps/` and `packages/`.

```bash
uv sync
cp config/attu-bot.sample.toml .secrets/attu-bot.toml
uv run python apps/bot/doom-bot.py bot
```

## development

see [docs/architecture.md](docs/architecture.md) for package layout and file roles; coding conventions and project rules live in `CLAUDE.md` and the skills under `.claude/skills/`.

### worktrees

multi-step work happens on a branch in `.claude/worktrees/<slug>/`. `scripts/dev-functions.zsh` holds the two helpers that close one out; source it from your shell rc:

| command | effect |
|---|---|
| `plan-merge <slug>` | fast-forward the branch into trunk, remove the worktree, delete the branch |
| `plan-remove <slug>` | drop the worktree and branch without merging (abandoned or superseded) |

`<slug>` is the worktree directory name. both resolve the branch by trying `phase/<slug>`, then `worktree-<slug>`, then the bare slug, so either naming works. run them from trunk in the main checkout; `plan-merge` refuses to run while the shell is on the branch it is merging.

### tests

primary path: run from the venv, no docker relaunch needed.

```bash
uv run python scripts/run_tests.py
```

docker is available as an alternative, but only for unit and component suites; the `tests` container has no `.secrets` mount, so integration tests can't find a config file that way.

```bash
docker compose -f docker-compose.dev.yml run --build --rm --quiet-build tests scripts/run_tests.py
```

what each suite needs:

- unit: no db needed; either path works
- component: needs a mongo instance; `docker compose -f docker-compose.dev.yml up -d mongo` before a venv run, or the docker `tests` path; point a venv run at it with `TEST_DB_URL=mongodb://localhost:27017/doombot`
- integration: needs a valid, current `.secrets/attu-bot.toml`; its `config_version` must be at or above what `nova_core/config.py`'s `__config_version__` requires, or the run fails with a version-gate error

`ATTU_CONFIG_FILE` and `TEST_DB_URL` point at two different things, not one value with a precedence order:

- `ATTU_CONFIG_FILE` (and the toml's `database.url`) govern integration tests and real bot startup
- `TEST_DB_URL` only governs `tests/conftest.py`'s component-test fixtures, which connect to mongo directly and never call `config.on_init()`

a git worktree never carries `.secrets/` (gitignored, not copied by `git worktree add`), so integration tests run from a worktree need `ATTU_CONFIG_FILE` pointed at the main checkout's copy, or a symlink to it:

```bash
ATTU_CONFIG_FILE=<main-checkout>/.secrets/attu-bot.toml uv run python scripts/run_tests.py
```

the dev-compose `mongo` service carries two workarounds the component suite depends on (a `GLIBC_TUNABLES` rseq override for newer host kernels and a raised `nofile` ulimit); see the comments on that service before changing it.

### linting

```bash
uv run ruff check .
uv run ruff format --check .
```

## credits

- progress bar emojis from [emoji.gg Progress Bar Pack](https://emoji.gg/pack/7783-progress-bar)

## license

Copyright (c) 2026 John Hancock, The Attu Project

This project is licensed under the Apache License, Version 2.0; see [LICENSE](LICENSE) for full text
