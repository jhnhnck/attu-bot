# AttuBot

A Discord bot for the Attu Project that automates in-universe timekeeping, year-transition announcements, wiki management, and related server utilities.

## Features

- tracks in-universe time and automates year transitions - announcements, channel name updates, wiki edits
- retrieves year info and links to specific years in lore channels
- manages a starboard, message backfill, and moderation logging
- egg collection game with rarity-based hatching and trading

## Commands

### Users

- **/ping**: checks if the bot is online

- **/year**: utilities related to current, past, or future years
  - **/year check [year]**: prints year info (start date, end date, duration); defaults to next year if omitted
  - **/year link \<year\> [channel]**: links to the specified year in a lore channel; defaults to #lore-news
  - **/year search \<year\>**: prints a search query for timelining

- **/wiki**: wiki lookup and management
  - **/wiki random**: gets a random page from the wiki
  - **/wiki lookup \<query\>**: searches the wiki for relevant pages

- **/eggs**: egg collection game
  - **/eggs hatch**: hatch your next ready egg
  - **/eggs view**: view your egg collection thread
  - **/eggs give \<user\> [rarity]**: give one of your eggs to another user
  - **/eggs progress**: view your collection progress by rarity with progress bars

- **/stars**: starboard browsing and leaderboards
  - **/stars random**: shows a random message with 2 or more stars
  - **/stars lost**: shows a random message with exactly 1 star
  - **/stars recheck \<message_link\>**: force-updates the starboard post for a specific message
  - **/stars most-stars**: top users by total stars received
  - **/stars most-starred**: top users by number of messages on the starboard
  - **/stars most-given**: top users by total stars given

### Admin

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

- **/debug**: diagnostic info (admin only)
  - **/debug version**: current version and container build time
  - **/debug scheduler**: currently running background tasks
  - **/debug year_stats**: current state of timekeeping calculations
  - **/debug message_stats [channel]**: count of stored messages for a channel or the whole guild
  - **/debug message \<link\>**: raw info about a specific message
  - **/debug dump_config**: prints loaded config to console
  - **/debug dump_starboard**: dumps 50 random starboard bot messages to a file
  - **/debug force_error**: throws an internal error (for testing)

- **/fix**: repair and rebuild commands (bot owner only)
  - **/fix logo**: forces the logo update task to run immediately
  - **/fix year_links**: forces the year links channel to be rebuilt
  - **/fix messages \<channel\>**: verifies and backfills any missing stored messages in a channel
  - **/fix author_names [user]**: re-resolves usernames and updates all stored messages
  - **/fix reconcile [days]**: scans recent guild history and reconciles starboard state
  - **/fix emoji**: uploads and verifies all custom emojis on the secondary server
  - **/fix starboard recount**: re-fetches live Discord reactions and updates starboard counts
  - **/fix starboard recover [days]**: scans the starboard channel and restores any missing db records
  - **/fix starboard regen**: rebuilds every starboard post for this guild
  - **/fix starboard purge \<message_link\>**: removes a message from the starboard database

## Setup

### Configuration

1. copy `config/sample.env` to `.env` and fill in postgres credentials
2. copy `config/attu-bot.sample.toml` to `.secrets/attu-bot.toml` and fill in your values (bot token, wiki credentials, authorized guild IDs, etc.); the compose stack mounts both files into each container
3. runtime guild settings (epoch, channels, roles, theme) live in MongoDB and can be updated via bot commands

### Docker (recommended)

```bash
git clone https://github.com/jhnhnck/attu-bot.git && cd attu-bot
mkdir -p .secrets
cp config/sample.env .env
cp config/attu-bot.sample.toml .secrets/attu-bot.toml
vim .env .secrets/attu-bot.toml
docker compose up --build -d
docker compose logs -f
```

### Local development

uv + pnpm workspace; member packages live under `apps/` and `packages/`.

```bash
uv venv && source .venv/bin/activate
uv sync
pnpm install
cp config/attu-bot.sample.toml .secrets/attu-bot.toml
python apps/bot/doom-bot.py bot
```

## Development

See [docs/architecture.md](docs/architecture.md) for full architecture, coding conventions, and contributor guidelines.

### Tests

```bash
docker compose run --build --rm --quiet-build tests scripts/run_tests.py
```

### Linting

```bash
ruff check .
ruff format --check .
npm run lint
```

## Credits

- Progress bar emojis from [emoji.gg Progress Bar Pack](https://emoji.gg/pack/7783-progress-bar)

## License

Copyright (c) 2026 John Hancock, The Attu Project

This project is licensed under the Apache License, Version 2.0; See [LICENSE](LICENSE) for full text
