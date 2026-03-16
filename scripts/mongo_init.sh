#!/bin/bash
# runs inside mongo:8 container during /docker-entrypoint-initdb.d/ phase (no auth yet).
# called automatically when /data/db is empty - which is always, since docker-compose.dev.yml
# mounts /data/db as tmpfs.

if [ -d /tmp/seeds/doombot-seed ]; then
    echo "restoring db from seed directory..."
    mongorestore /tmp/seeds/doombot-seed
    echo "seed restore complete"
else
    echo "no seed found at assets/doombot-seed - starting with empty db"
fi

touch /tmp/seed_ready
