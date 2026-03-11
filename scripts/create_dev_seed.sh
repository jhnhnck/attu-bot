#!/bin/bash
# copies an existing mongodump backup directory to assets/doombot-seed/ for use by the dev db.
# usage: bash scripts/create_dev_seed.sh <backup_dir>
# example: bash scripts/create_dev_seed.sh /srv/backups/attu-bot/2026-03-06_220000
set -e

SRC="${1:-}"
DEST="assets/doombot-seed"

if [[ -z "$SRC" ]]; then
    echo "usage: bash scripts/create_dev_seed.sh <backup_dir>"
    exit 1
fi

if [[ ! -d "$SRC" ]]; then
    echo "error: $SRC is not a directory"
    exit 1
fi

rm -rf "$DEST"
cp -r "$SRC" "$DEST"
echo "seed copied to $DEST"
