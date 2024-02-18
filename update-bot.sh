#!/bin/bash

docker compose down

sftp discordbot-dev <<END
lcd /srv/attu/attu-bot
cd /home/jhnhnck/attu-bot
get -R *
END

docker compose up -d --build
