# Dev Environment Setup

The dev worktree at `/srv/services/doom-bot-dev` is a git worktree on a local `dev` branch.
Changes are never pushed directly from `dev` - only `trunk` is pushed to the remote.
The dev compose stack (`docker-compose.dev.yml`) runs the legacy web service against an ephemeral ferretdb plus a `tests` profile - no live discord connection.

## One-time setup

```bash
# 1. create the git worktree on a local-only branch
git worktree add /srv/services/doom-bot-dev dev

# 2. enter the worktree and copy secrets
cd /srv/services/doom-bot-dev
mkdir -p .secrets
cp /srv/services/doom-bot/.env .env
cp config/attu-bot.sample.toml .secrets/attu-bot.toml
```

Edit `.secrets/attu-bot.toml` with at minimum:
- `[database] url = "mongodb://<POSTGRES_USER>:<POSTGRES_PASSWORD>@ferret:27017/doombot?authSource=admin"` - paste the literal values from `.env` (the toml is not env-substituted at load). `authSource=admin` is required because ferretdb authenticates through the postgres role table; the `/doombot` path is informational (the bot reads the db name from `database.name`).
- `[auth.bot] token = "..."` - the prod token is fine; `TEST_MODE=1` means the bot never opens a discord gateway connection during tests

```bash
# 3. (optional) seed the dev db from prod - see section below
cd /srv/services/doom-bot
bash scripts/create_dev_seed.sh
```

## Running tests

```bash
cd /srv/services/doom-bot-dev
docker compose -f docker-compose.dev.yml run --build --rm --quiet-build tests
```

The ferret/postgres pair starts fresh on every run (postgres uses a tmpfs data dir) and `ferret-init` reseeds it from `apps/bot/assets/doombot-seed/`.
If the seed dir is missing, the database starts empty - tests create their own data and are unaffected.

## local venv (optional, for ide support)

no `.venv` exists in the project root yet; create one and install all deps for ide type checking and autocomplete:

```bash
cd /srv/services/doom-bot-dev
uv venv
uv sync
```

activate with `source .venv/bin/activate` or point your ide to `.venv/bin/python`. if a `.venv` already exists, skip `uv venv` and just re-run the install.

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

### one-time secret migration on prod

The first deploy after the `.secrets/` move needs a manual file shuffle (`attu-bot.toml` moves under `.secrets/`; `.env` stays at the project root so docker compose auto-discovers it for variable interpolation):

```bash
cd /srv/services/doom-bot
mkdir -p .secrets
mv apps/bot/assets/attu-bot.toml .secrets/attu-bot.toml
# then edit .secrets/attu-bot.toml and set:
#   [paths]
#   assets = "/home/doom/apps/bot/assets"
```

The `paths.assets` edit is required — `hatch.toml` is now resolved through it, so a stale `./assets` value will fail at startup with `missing hatch.toml`.

## Refreshing the seed from prod

`create_dev_seed.sh` takes a `.tar.bz2` backup archive as its only argument and unpacks it into `apps/bot/assets/doombot-seed/`. run it from the prod directory whenever you want dev to start from a known prod backup:

```bash
cd /srv/services/doom-bot
bash scripts/create_dev_seed.sh /srv/backups/attu-bot/<timestamp>.tar.bz2
# output: /srv/services/doom-bot-dev/apps/bot/assets/doombot-seed/
```

the seed dir is gitignored. between compressed backups you can also stage one manually:
```bash
rm -rf /srv/services/doom-bot-dev/apps/bot/assets/doombot-seed
cp -r /srv/backups/attu-bot/<timestamp> /srv/services/doom-bot-dev/apps/bot/assets/doombot-seed
```

---

## metadata

```yaml
last_updated: 2026-05-06
```
