# builder for svg converter
FROM rust:bookworm AS builder
RUN cargo install --version ^0.46 resvg

# doom-bot container
FROM python:3.13-bookworm
ENV TZ="America/New_York"
ENV FORCE_COLOR=1

# setup runtime
RUN mkdir -p /home/doom/
WORKDIR /home/doom/
RUN useradd --home-dir /home/doom --uid 1000 doom; \
    chown -Rc doom:doom /home/doom;

# install system dependencies
RUN --mount=type=cache,target=/var/lib/apt \
    set -eux; \
    apt update; \
    apt install -y \
        curl \
        neovim \
        sqlite3;

# install resvg
COPY --from=builder /usr/local/cargo/bin/resvg /usr/local/bin/resvg

# run everything else as a standard user
USER doom

COPY ./requirements.txt /home/doom/

# install user dependencies
RUN --mount=type=cache,target=/home/doom/.cache/,uid=1000,gid=1000 \
    pip install --user -r ./requirements.txt;

# include docs/license with code
COPY ./LICENSE ./README.md ./attu-bot.py /home/doom/
COPY ./attubot /home/doom/attubot

# stamp container date for debugging purposes
RUN printf 'BUILD_TIME="%s"\n' "$(date)" >> /home/doom/.env;
