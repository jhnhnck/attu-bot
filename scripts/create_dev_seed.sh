#!/bin/bash
# creates dev seed from a backup archive.
# strips large bot-only collections to keep the seed small for web dev.
# usage: bash scripts/create_dev_seed.sh <backup.tar.bz2>
# example: bash scripts/create_dev_seed.sh /srv/backups/attu-bot/2026-03-17_030000.tar.bz2
set -e

SRC="${1:-}"
DEST="apps/bot/assets/doombot-seed"

if [[ -z "$SRC" ]]; then
    echo "usage: bash scripts/create_dev_seed.sh <backup.tar.bz2>"
    exit 1
fi

if [[ ! -f "$SRC" ]]; then
    echo "error: $SRC not found"
    exit 1
fi

TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

echo "extracting $SRC..."
tar -xjf "$SRC" -C "$TMP"

EXTRACTED=$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)
if [[ -z "$EXTRACTED" ]]; then
    echo "error: no directory found in archive"
    exit 1
fi

# strip heavy collections the web interface doesn't need
DB_DIR=$(find "$EXTRACTED" -mindepth 1 -maxdepth 1 -type d | head -1)
if [[ -n "$DB_DIR" ]]; then
    for coll in messages chat_sources families chat_characters; do
        rm -f "$DB_DIR/$coll.bson" "$DB_DIR/$coll.metadata.json"
    done
    # remove stale test collections
    rm -f "$DB_DIR"/test_*_messages.bson "$DB_DIR"/test_*_messages.metadata.json
    echo "stripped heavy collections from seed"
fi

rm -rf "$DEST"
mv "$EXTRACTED" "$DEST"
echo "seed ready at $DEST"
