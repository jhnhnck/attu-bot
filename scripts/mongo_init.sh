#!/bin/bash
# runs inside mongo:8 container during /docker-entrypoint-initdb.d/ phase (no auth yet).
# called automatically when /data/db is empty - which is always, since docker-compose.dev.yml
# mounts /data/db as tmpfs.
if [ -f /tmp/seeds/doombot-seed.archive ]; then
    echo "restoring db from seed archive..."
    mongorestore --archive=/tmp/seeds/doombot-seed.archive --gzip
    echo "seed restore complete"
else
    echo "no seed found at assets/doombot-seed.archive - starting with empty db"
fi
