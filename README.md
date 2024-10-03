# Doom Bot

DoomBot was designed for the Attu Project to assist with essential timekeeping features and various other utilities

## Features

- Keep track of time progression and automate the tasks needed upon a new year transition such as making announcements, updating channel names, and editing the wiki homepage
- Retrieve information about specific years and link to certain points in time within lore channels
- Provide administrative tools and debug commands for server and wiki management

## Timekeeping Process

The bot maintains a timekeeping system that calculates the current year and determines the transition to the next year based on a defined epoch and its length

- The starting point for in-universe time is defined in the configuration file, including the initial year and the length of each year in days
- The current year is calculated by determining the number of days that have passed since the epoch and adding this to the initial year
- The bot monitors total days passed to accurately handle transitions to the next year based on a defined trigger time
- A timestamp for each passed year is stored in Discord snowflake format to reference past years and link to specific moments within the lore channels

### Simplified Formula

```
current_year = epoch_year + (days_since_epoch // epoch_length) - (1 IF (days_since_epoch MOD epoch_length) == 0 AND current_time < trigger_time ELSE 0)
```

## Build / Setup

1. Clone the repository:

```bash
$ git clone https://github.com/jhnhnck/attu-bot.git

$ cd attu-bot
```

2. Make a copy of the sample configuration file and replace the placeholders with your Discord bot token, wiki API key, page and username, channel IDs, role ID for leaders, epoch settings (time, year, paused status, and length), bot owner's user ID, actual server IDs for guilds, and any existing year timestamps (in Discord snowflake format):
```bash
$ cp ./config/attu-bot.sample.json ./attu-bot.json

$ vim ./attu-bot.json
```

3. Run the following command to build the Docker image and start the bot:

```bash
$ docker compose up --build -d
```

## Usage

Once the bot is running, invite it to your Discord server with the link printed to the console (use `docker compose logs` to view)

Use the following commands to interact with the bot:

- **/check_year [year]**: Prints out information related to a specified year such as the start date, end date, and year duration; if not specified, year defaults to the next year
- **/link_year <year> [channel]**: Links to the specified year in a lore channel; if not specified, channel defaults to #lore-news
- **/wiki_block <user> <reason>**: Blocks a specified user from the wiki (Admin only)
- **/debug <option>**: Allows administrators to check the bot's version, retrieve statistics for the current year, or force an error for testing and troubleshooting purposes (Admin only)
- **/admin <option> [number]**: Allows administrators to execute various options such as controlling time by incrementing, dilating, pausing, or resuming it (Admin only)

## License

This project is licensed under the Apache License, Version 2.0; See [LICENSE](LICENSE) for full text
