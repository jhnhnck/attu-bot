#!/bin/bash
# creates a mongodump seed archive from the running prod db.
# run from /srv/services/doom-bot (the prod directory).
# usage: bash scripts/create_dev_seed.sh [output_path]
set -e

DEST="${1:-/srv/services/doom-bot-dev/assets/doombot-seed.archive}"

if ! docker compose ps mongo --format '{{.State}}' 2>/dev/null | grep -q running; then
    echo "error: prod mongo container is not running"
    exit 1
fi

echo "creating dev seed from prod db..."
docker compose exec mongo mongodump \
    --archive=/tmp/doombot-seed.archive \
    --gzip \
    --db=doombot
docker compose cp mongo:/tmp/doombot-seed.archive "$DEST"
docker compose exec mongo rm /tmp/doombot-seed.archive
echo "seed saved to $DEST"
