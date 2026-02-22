# Doom Bot

DoomBot was designed for the Attu Project to assist with essential timekeeping features and various other utilities

## Features

- Keep track of time progression and automate the tasks needed upon a new year transition such as making announcements, updating channel names, and editing the wiki homepage
- Retrieve information about specific years and link to certain points in time within lore channels
- Provide administrative tools and debug commands for server and wiki management

## Timekeeping Process

The bot maintains a timekeeping system that calculates the current year and determines the transition to the next year based on a defined epoch and its length

- The starting point for in-universe time is defined in the configuration, including the initial year and the length of each year in days
- The current year is calculated by determining the number of days that have passed since the epoch and adding this to the initial year
- The bot monitors total days passed to accurately handle transitions to the next year based on a defined trigger time
- A timestamp for each passed year is stored in Discord snowflake format to reference past years and link to specific moments within the lore channels

### Simplified Formula

```
current_year = epoch_year + (days_since_epoch // epoch_length) - (1 IF (days_since_epoch MOD epoch_length) == 0 AND current_time < trigger_time ELSE 0)
```

## Configuration

AttuBot uses a **three-tier configuration system**:

### Tier 1 — Environment Variables (`.env`)

Only two values belong here. Copy `config/sample.env` to `.env`:

| Variable | Purpose |
|---|---|
| `ATTU_CONFIG_FILE` | Path to the TOML config file (default: `./assets/attu-bot.toml`) |
| `BUILD_TIME` | Stamped automatically at container build time — do not set manually |

Everything else that was previously in `.env` has been moved into the TOML file.

### Tier 2 — TOML Config File (secrets + read-only config)

The TOML file holds all **secrets and static configuration** that must be present before the bot can start. Copy `config/attu-bot.sample.toml` to `assets/attu-bot.toml` and fill in your values:

```toml
config_version = "2.1.0"

[paths]
# Path to assets directory (templates, static files, favicon)
assets = "./assets"

[database]
# MongoDB connection settings
url = "mongodb://localhost:27017"
name = "doombot"

[auth.bot]
# Discord bot token — from the Discord Developer Portal
token = "TOKEN_GOES_HERE"

[auth.web]
# Secret key for session signing — generate with:
#   python -c "import secrets; print(secrets.token_hex(32))"
secret_key = "your-secret-key-here"

[auth.webauthn]
# WebAuthn / Passkey settings for the web interface
rp_id = "localhost"              # domain only, e.g. "example.com"
rp_name = "AttuBot Configurator"
origin = "http://localhost:5000" # full origin, e.g. "https://example.com"

[auth.wiki]
key = "KEY_GOES_HERE"
page = "Example:Home"
user = "WikiBot@WikiBot"
endpoint = "https://example.org"

[discord.guilds]
authorized = [1000000000000000000]
```

### Tier 3 — MongoDB (configurable runtime settings)

Guild-level and system-level settings that can be changed at runtime are stored in MongoDB. These include epoch configuration, channel/role IDs, theme, and other values that may be updated via bot commands or the web interface. See [Configuration Keys](#configuration-keys) below for the full list.

---

## Build / Setup

1. Clone the repository:

```bash
$ git clone https://github.com/jhnhnck/attu-bot.git

$ cd attu-bot
```

2. Make a copy of the sample configuration file and replace the placeholders with your Discord bot token, wiki API details and authorized guilds:
```bash
$ cp ./config/attu-bot.sample.toml ./assets/attu-bot.toml

$ vim ./assets/attu-bot.toml
```

3. Run the following command to build the Docker image and start the bot:
```bash
$ docker compose up --build -d
```

## Usage

Once the bot is running, invite it to your Discord server with the link printed to the console (use `docker compose logs` to view)

Use the following commands to interact with the bot:

### Users

- **/ping**: Simple command to test if the bot is online

- **/year**: Utilities related to current, past or future years
  - **/year check <year>**: Prints out information related to a specified year such as the start date, end date, and year duration; if not specified, year defaults to the next year
  - **/year link <year> [channel]**: Links to the specified year in a lore channel; if not specified, channel defaults to #lore-news
  - **/year search <year>**: Prints search query for timlining

- **/wiki**: Utilities for managing and querying the wiki
  - **/wiki lookup <query> [limit]**: Search the wiki for relevent pages; if not specified, limit defaults to 1

### Admin

- **/config**: ~~Modify various options for bot behavior (Admin only)~~ *Currently unavailable*
  - ~~**/config delete <key>**: Delete a specific key from the config table~~
  - ~~**/config get <key>**: Fetch the value of a configuration~~
  - ~~**/config list**: List out the available config options~~
  - ~~**/config set <key> <value>**: Set the value of a configuration~~
  - ~~**/config show**: Show the entire guild configuration~~

- **/debug**: Prints information for testing and troubleshooting purposes (Admin only)
  - **/debug dump_config**: Prints currently loaded config values to console
  - **/debug force_error**: Causes an internal error to be thrown
  - **/debug message <link>**: Print information about a specific message (warning: not very user readable)
  - **/debug version**: Displays the current version and container build time
  - **/debug year_stats**: Returns the current state of time tracking calculations

- **/marker**: Utilities related to managing year markers (Admin Only)
  - **/marker save <year> <link> [force]**: Updates marker to point to a different message
  - **/marker set <year> <snowflake>**: Sets marker timestamp for when a specifc year starts (channel=guild)
  - **/marker clear <year> <channel>**: Removes marker for a specific channel and year (will attempt to locate again next time /year link is ran)

- **/query**: Performs searches for specific messages
  - **/query pins <channel>**: Finds all the "pinned a message" messages in a channel (Resource Intensive)

- **/time**: Modify various options controlling the passage of time (Admin only)
  - **/time advance**: Manually advance to the next year, ignoring all checks
  - **/time dilate <days>**: Adjust the rate at which time progresses
  - **/time pause**: Pause the passage of time
  - **/time resume**: Resume the passage of time

- **/wiki**: Utilities for managing and querying the wiki
  - **/wiki block <user> <reason>**: Blocks a specified user from the wiki (Admin only)

## Configuration Keys

### Global

- **0/error_log**: [1000000000000000000, 1000000000000000000]
- **0/error_hook**: 'https://discord.com/api/webhooks/1000000000000000000/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
- **0/primary_guild**: 1000000000000000000

### Guild Specific

If using the `[Import]` directive within the config file, use the following format: `<guild id>/<key name>`

- Channels:
  - **channels.activity**: 1000000000000000000
  - **channels.announcements**: 1000000000000000000
  - **channels.lore_channels**: [1000000000000000000, 1000000000000000000, 1000000000000000000, 1000000000000000000, 1000000000000000000]
  - **channels.meta_chat**: 1000000000000000000
  - **channels.year_links**: 1000000000000000000
  - **channels.year_vc**: 1000000000000000000

- Epoch:
  - **epoch.length**: 14
  - **epoch.paused**: false
  - **epoch.rollover_time**: "17:00"
  - **epoch.time**: 1660101177
  - **epoch.year**: 1

- Roles:
  - **roles.announcements**: 1000000000000000000

- Users:
  - **users.markers**: [1000000000000000000, 1000000000000000000]



## Development

### Setup

1. Create a Python 3.13+ virtual environment:

Using [pyenv](https://github.com/pyenv/pyenv):
```bash
$ pyenv virtualenv 3.13 doom-bot
$ pyenv activate doom-bot
```

Or using the built-in `venv` module:
```bash
$ python3.13 -m venv .venv
$ source .venv/bin/activate
```

2. Install dependencies:
```bash
$ pip install -r requirements.txt -r requirements-dev.txt
```

### Running Tests

```bash
$ pytest
```

Tests are located in `tests/` and configured via `pyproject.toml`. The test suite uses [freezegun](https://github.com/spulec/freezegun) to pin wall-clock time for deterministic calendar calculations.

Tests marked with `xfail` document known bugs that are expected to fail until the underlying issue is fixed. When a fix lands, these tests will automatically flag as `XPASS` (unexpected pass), indicating the marker should be removed.

## License

Copyright (c) 2026 John Hancock, The Attu Project

This project is licensed under the Apache License, Version 2.0; See [LICENSE](LICENSE) for full text
