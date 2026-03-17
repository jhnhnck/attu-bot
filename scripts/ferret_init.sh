#!/bin/bash
# runs in tester container; waits for ferretdb, restores seed, signals ready.

until mongosh --host ferret:27017 --eval 'db.adminCommand({ping:1})' --quiet 2>/dev/null; do
    sleep 1
done

if [ -d /tmp/seeds/doombot-seed ]; then
    echo "restoring db from seed..."
    mongorestore --host ferret:27017 /tmp/seeds/doombot-seed
    echo "seed restore complete"
else
    echo "no seed found at assets/doombot-seed - starting with empty db"
fi
