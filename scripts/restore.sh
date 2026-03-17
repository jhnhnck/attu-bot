#!/bin/bash
# restores a database backup to the production ferretdb instance.
# run from the doom-bot root directory on the host.
# usage: bash scripts/restore.sh <backup.tar.bz2>
# example: bash scripts/restore.sh /srv/backups/attu-bot/2026-03-17_030000.tar.bz2
#
# pre-restore checklist:
#   1. stop bot services: docker compose stop core web ingestor
#   2. run this script
#   3. restart: docker compose start core web ingestor
set -e

BACKUP="${1:-}"
BACKUP_ROOT="/srv/backups/attu-bot"
CONTAINER_BACKUP_ROOT="/home/doom/backups"
RESTORE_TMP_NAME=".restore-tmp"

if [[ -z "$BACKUP" ]]; then
    echo "usage: bash scripts/restore.sh <backup.tar.bz2>"
    echo "example: bash scripts/restore.sh /srv/backups/attu-bot/2026-03-17_030000.tar.bz2"
    exit 1
fi

if [[ ! -f "$BACKUP" ]]; then
    echo "error: backup file not found: $BACKUP"
    exit 1
fi

echo "restoring from: $BACKUP"
echo "WARNING: drops and replaces all data in 'doombot'."
echo "ensure 'core', 'web', and 'ingestor' services are stopped."
read -r -p "proceed? [y/N] " confirm
[[ "$confirm" =~ ^[yY]$ ]] || { echo "aborted"; exit 0; }

RESTORE_TMP="$BACKUP_ROOT/$RESTORE_TMP_NAME"
RESTORE_TMP_CONTAINER="$CONTAINER_BACKUP_ROOT/$RESTORE_TMP_NAME"

rm -rf "$RESTORE_TMP"
mkdir -p "$RESTORE_TMP"
trap "rm -rf $RESTORE_TMP" EXIT

echo "extracting archive..."
tar -xjf "$BACKUP" -C "$RESTORE_TMP"
DUMP_DIR_NAME=$(find "$RESTORE_TMP" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | head -1)

if [[ -z "$DUMP_DIR_NAME" ]]; then
    echo "error: no dump directory found in archive"
    exit 1
fi

echo "running mongorestore..."
docker compose exec core mongorestore \
    --host ferret:27017 \
    --drop \
    "$RESTORE_TMP_CONTAINER/$DUMP_DIR_NAME"

echo "restore complete"
