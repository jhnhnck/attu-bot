#!/bin/bash
# creates dev seed from a backup archive.
# usage: bash scripts/create_dev_seed.sh <backup.tar.bz2>
# example: bash scripts/create_dev_seed.sh /srv/backups/attu-bot/2026-03-17_030000.tar.bz2
set -e

SRC="${1:-}"
DEST="assets/doombot-seed"

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

rm -rf "$DEST"
mv "$EXTRACTED" "$DEST"
echo "seed ready at $DEST"
