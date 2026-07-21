# dev environment setup

the main checkout lives at `/home/jhn/Projects/doom-bot` on the `trunk` branch. the prod worktree lives at `/srv/services/doom-bot` on the `prod` branch.

## one-time setup

```bash
# already cloned; just copy secrets from the sample
cd /home/jhn/Projects/doom-bot
mkdir -p .secrets
cp config/attu-bot.sample.toml .secrets/attu-bot.toml
```

edit `.secrets/attu-bot.toml` with at minimum:

- `[database] url = "mongodb://<POSTGRES_USER>:<POSTGRES_PASSWORD>@ferret:27017/doombot?authSource=admin"` - paste the literal values from `.env` (the toml is not env-substituted at load). `authSource=admin` is required because ferretdb authenticates through the postgres role table; the `/doombot` path is informational (the bot reads the db name from `database.name`).
- `[auth.bot] token = "..."` - the prod token is fine; `TEST_MODE=1` means the bot never opens a discord gateway connection during tests
- `[bridge] secret = "<hex>"` - generate with `python -c "import secrets; print(secrets.token_hex(32))"`; must be present or both bot and server crash on startup

```bash
# (optional) seed the dev db from prod - see section below
bash scripts/create_dev_seed.sh /srv/backups/attu-bot/<timestamp>.tar.bz2
```

## running tests

```bash
cd /home/jhn/Projects/doom-bot
docker compose -f docker-compose.dev.yml run --build --rm --quiet-build tests
```

the ferret/postgres pair starts fresh on every run (postgres uses a tmpfs data dir) and `ferret-init` reseeds it from `apps/bot/assets/doombot-seed/`. if the seed dir is missing, the database starts empty - tests create their own data and are unaffected.

## local venv (optional, for ide support)

```bash
cd /home/jhn/Projects/doom-bot
uv venv
uv sync
```

activate with `source .venv/bin/activate` or point your ide to `.venv/bin/python`. if a `.venv` already exists, skip `uv venv` and just re-run `uv sync`.

## deploying to prod

```bash
# push trunk to remote
cd /home/jhn/Projects/doom-bot
git push origin trunk

# pull and rebuild in the prod worktree
cd /srv/services/doom-bot
git pull
docker compose up --build -d
```

## refreshing the seed from prod

`create_dev_seed.sh` takes a `.tar.bz2` backup archive as its only argument and unpacks it into `apps/bot/assets/doombot-seed/`. run it from the main checkout:

```bash
cd /home/jhn/Projects/doom-bot
bash scripts/create_dev_seed.sh /srv/backups/attu-bot/<timestamp>.tar.bz2
```

the seed dir is gitignored. between compressed backups you can also stage one manually:

```bash
rm -rf apps/bot/assets/doombot-seed
cp -r /srv/backups/attu-bot/<timestamp> apps/bot/assets/doombot-seed
```

---

## metadata

```yaml
last_updated: 2026-07-21
```
