# builder for svg converter
FROM rust:bookworm AS builder
RUN cargo install --version ^0.46 resvg

# git-info stage: stamps version and build time into __init__.py via sed
FROM python:3.13-bookworm AS git-info
ENV TZ="America/New_York"
RUN apt-get update -qq && apt-get install -y -qq git
WORKDIR /src
COPY . .
RUN set -eux; \
    GIT_COMMIT="$(git rev-parse --short HEAD)"; \
    GIT_CHANGED="$(git diff HEAD --numstat | awk '{s+=$1+$2} END {print s+0}')"; \
    BUILD_TIME="$(date '+%a %b %d %H:%M:%S %Z %Y')"; \
    sed -i "s|__version__ = '\([^']*\)'|__version__ = '\1-${GIT_COMMIT}+${GIT_CHANGED}'|" attubot/__init__.py; \
    sed -i "s|__build_time__ = '[^']*'|__build_time__ = '${BUILD_TIME}'|" attubot/__init__.py;

# doom-bot container
FROM python:3.13-bookworm AS doombox
ENV TZ="America/New_York"
ENV FORCE_COLOR=1
ARG DOOM_HOME="/home/doom"

# setup runtime
RUN mkdir -p $DOOM_HOME/
WORKDIR $DOOM_HOME/
RUN useradd --home-dir /home/doom --uid 1000 doom; \
    chown -Rc doom:doom /home/doom;

# install system dependencies
RUN --mount=type=cache,target=/var/lib/apt \
    set -eux; \
    apt-get update; \
    apt-get install -qq -y \
    curl \
    neovim \
    zsh;

SHELL [ "/usr/bin/zsh", "-euc" ]

# TODO: Update this to latest version
RUN --mount=type=cache,target=/var/lib/apt \
    curl -fsSL "https://fastdl.mongodb.org/tools/db/mongodb-database-tools-debian12-x86_64-100.14.1.deb" -o "/tmp/mongodb-database-tools.deb"; \
    dpkg -i "/tmp/mongodb-database-tools.deb";

# install resvg
COPY --from=builder /usr/local/cargo/bin/resvg /usr/local/bin/resvg

# run everything else as a standard user
USER doom

COPY --chown=doom:doom ./requirements.txt $DOOM_HOME/

# install user dependencies
RUN --mount=type=cache,target=$DOOM_HOME/.cache/,uid=1000,gid=1000 \
    pip install --user -r ./requirements.txt; \
    python -m compileall $HOME/attubot;

# include docs/license with code
COPY --chown=doom:doom ./LICENSE ./README.md ./attu-bot.py $DOOM_HOME/
COPY --chown=doom:doom ./attubot $DOOM_HOME/attubot
COPY --chown=doom:doom ./assets/templates $DOOM_HOME/assets/templates
COPY --chown=doom:doom ./assets/static $DOOM_HOME/assets/static

# stamp version and build time into __init__.py from git-info stage
COPY --from=git-info --chown=doom:doom /src/attubot/__init__.py $DOOM_HOME/attubot/__init__.py

# --- for running tests inside docker ---
FROM doombox AS tester
USER root

# Install Node.js for JavaScript tests
RUN --mount=type=cache,target=/var/lib/apt \
    curl -fsSL "https://deb.nodesource.com/setup_22.x" -o "/tmp/setup_22.x"; \
    bash /tmp/setup_22.x; \
    apt-get install -y -qq nodejs;

USER doom
WORKDIR /home/doom

# copy extra needed files
COPY --chown=doom:doom \
    ./requirements-dev.txt \
    ./package.json \
    ./package-lock.json \
    ./pyproject.toml \
    ./eslint.config.js \
    ./vitest.config.js \
    $DOOM_HOME/

COPY --chown=doom:doom ./tests $DOOM_HOME/tests
COPY --chown=doom:doom ./scripts $DOOM_HOME/scripts

# install python dev dependencies
RUN --mount=type=cache,target=$DOOM_HOME/.cache/,uid=1000,gid=1000 \
    pip install --user -r ./requirements-dev.txt;

# Install npm dependencies
RUN npm clean-install;
