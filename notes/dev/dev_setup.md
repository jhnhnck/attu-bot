# Dev Environment Setup

The dev worktree at `/srv/services/doom-bot-dev` is a git worktree on a local `dev` branch.
Changes are never pushed directly from `dev` - only `trunk` is pushed to the remote.
The dev compose stack (`docker-compose.dev.yml`) runs tests only - no live Discord connection.

## One-time setup

```bash
# 1. create the git worktree on a local-only branch
git worktree add /srv/services/doom-bot-dev dev

# 2. enter the worktree and copy secrets
cd /srv/services/doom-bot-dev
cp /srv/services/doom-bot/.env .env
cp config/attu-bot.sample.toml assets/attu-bot.toml
```

Edit `assets/attu-bot.toml` with at minimum:
- `[database] url = "mongodb://doom:PASS@mongo:27017"` where `PASS` matches `MONGO_INITDB_ROOT_PASSWORD` in `.env`
- `[auth.bot] token = "..."` - the prod token is fine; `TEST_MODE=1` means the bot never opens a Discord gateway connection during tests

```bash
# 3. (optional) seed the dev db from prod - see section below
cd /srv/services/doom-bot
bash scripts/create_dev_seed.sh
```

## Running tests

```bash
cd /srv/services/doom-bot-dev
docker compose -f docker-compose.dev.yml run --build --rm tests
```

The mongo container starts fresh from the seed archive on every run (tmpfs data dir).
If no seed file exists, mongo starts empty - tests create their own data and are unaffected.

## Deploying to prod

```bash
# merge dev into trunk locally - dev branch is never pushed to remote
git checkout trunk
git merge --ff-only dev
git push origin trunk

# rebuild prod from the merged trunk
cd /srv/services/doom-bot
git pull
docker compose up --build -d
```

## Refreshing the seed from prod

Run from the prod directory any time you want dev to start from current prod state:

```bash
cd /srv/services/doom-bot
bash scripts/create_dev_seed.sh
# output: /srv/services/doom-bot-dev/assets/doombot-seed.archive
```

The seed file is gitignored. Pass a custom path as the first argument if needed:
```bash
bash scripts/create_dev_seed.sh /some/other/path/seed.archive
```
