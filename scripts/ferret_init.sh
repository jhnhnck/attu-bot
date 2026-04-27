#!/bin/bash
# runs in tester container; waits for ferretdb, restores seed, signals ready.
# only restores collections the web interface needs; skips large bot-only data.

echo "waiting for ferretdb..."
until bash -c 'echo > /dev/tcp/ferret/27017' 2>/dev/null; do
    sleep 1
done
echo "ferretdb is ready"

if [ -d /tmp/seeds/doombot-seed ]; then
    echo "restoring db from seed (web-only subset)..."
    mongorestore --host ferret:27017 \
        -u "$POSTGRES_USER" -p "$POSTGRES_PASSWORD" \
        --nsExclude='doombot.messages' \
        --nsExclude='doombot.chat_sources' \
        --nsExclude='doombot.families' \
        --nsExclude='doombot.chat_characters' \
        --nsExclude='doombot.test_*' \
        /tmp/seeds/doombot-seed
    echo "seed restore complete"
else
    echo "no seed found at assets/doombot-seed - starting with empty db"
fi
