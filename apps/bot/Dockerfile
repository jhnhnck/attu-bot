# builder for svg converter
FROM rust:bookworm AS builder
RUN set -eux; \
    cargo install --version ^0.46 resvg --quiet;

# git-info stage: stamps version and build time into __init__.py via sed
FROM alpine:3.21 AS git-info
ENV TZ="America/New_York"
RUN apk add --no-cache git tzdata
WORKDIR /src
COPY . .
RUN set -eux; \
    GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo 'dev')"; \
    BUILD_TIME="$(date '+%a %b %d %H:%M:%S %Z %Y')"; \
    sed -i "s|__version__ = '\([^']*\)'|__version__ = '\1-${GIT_COMMIT}'|" apps/bot/doom_bot/__init__.py; \
    sed -i "s|__build_time__ = '[^']*'|__build_time__ = '${BUILD_TIME}'|" apps/bot/doom_bot/__init__.py;

# doom-bot container base - system deps, application code, and Python packages
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS doombox
ENV TZ="America/New_York"
ENV FORCE_COLOR=1
ARG DOOM_HOME="/home/doom"
ENV VIRTUAL_ENV="$DOOM_HOME/.venv"
ENV PATH="$DOOM_HOME/.venv/bin:$PATH"
# doom_bot lives at apps/bot/doom_bot, attu_models at packages/shared-models/attu_models;
# both are workspace virtual packages (uv does not install them), so PYTHONPATH carries the import roots.
ENV PYTHONPATH="$DOOM_HOME/apps/bot:$DOOM_HOME/packages/shared-models:$DOOM_HOME/packages/attu-logging"

# setup runtime
RUN mkdir -p $DOOM_HOME/
WORKDIR $DOOM_HOME/
RUN useradd --home-dir /home/doom --uid 1000 doom; \
    chown -Rc doom:doom /home/doom;

# install system dependencies
RUN --mount=type=cache,target=/var/lib/apt \
    --mount=type=cache,target=/var/cache/apt \
    set -eux; \
    apt-get update -qq; \
    apt-get install -qq \
    curl \
    gnupg \
    neovim \
    zsh;

SHELL [ "/usr/bin/zsh", "-euc" ]

# repeat TODO: hardcoded version; keep updated
RUN --mount=type=cache,target=/var/lib/apt \
    curl -fsSL "https://fastdl.mongodb.org/tools/db/mongodb-database-tools-debian12-x86_64-100.15.0.deb" -o "/tmp/mongodb-database-tools.deb"; \
    dpkg -i "/tmp/mongodb-database-tools.deb";

# install resvg
COPY --from=builder /usr/local/cargo/bin/resvg /usr/local/bin/resvg

USER doom

# workspace manifests and lockfile (need every member's pyproject for uv sync to resolve)
COPY --chown=doom:doom ./pyproject.toml ./uv.lock $DOOM_HOME/
COPY --chown=doom:doom ./apps/bot/pyproject.toml $DOOM_HOME/apps/bot/pyproject.toml
COPY --chown=doom:doom ./apps/server/pyproject.toml $DOOM_HOME/apps/server/pyproject.toml
COPY --chown=doom:doom ./packages/shared-models/pyproject.toml $DOOM_HOME/packages/shared-models/pyproject.toml
COPY --chown=doom:doom ./packages/attu-logging/pyproject.toml $DOOM_HOME/packages/attu-logging/pyproject.toml

# install all service dependencies
RUN --mount=type=cache,target=$DOOM_HOME/.cache/,uid=1000,gid=1000 \
    uv venv && uv sync --no-install-project --no-dev --quiet;

# include docs/license with code
COPY --chown=doom:doom ./LICENSE ./README.md $DOOM_HOME/
COPY --chown=doom:doom ./apps/bot/doom-bot.py $DOOM_HOME/apps/bot/doom-bot.py
COPY --chown=doom:doom ./apps/bot/doom_bot $DOOM_HOME/apps/bot/doom_bot
COPY --chown=doom:doom ./apps/bot/assets/hatch.toml $DOOM_HOME/apps/bot/assets/hatch.toml
COPY --chown=doom:doom ./apps/bot/assets/static $DOOM_HOME/apps/bot/assets/static
COPY --chown=doom:doom ./packages/shared-models/attu_models $DOOM_HOME/packages/shared-models/attu_models
COPY --chown=doom:doom ./packages/attu-logging/attu_logging $DOOM_HOME/packages/attu-logging/attu_logging

# stamp version and build time into __init__.py from git-info stage
COPY --from=git-info --chown=doom:doom /src/apps/bot/doom_bot/__init__.py $DOOM_HOME/apps/bot/doom_bot/__init__.py

# --- for running tests inside docker ---
FROM doombox AS tester
USER root

# copy extra needed files (as root so scripts can be chmod'd)
COPY --chown=doom:doom ./tests $DOOM_HOME/tests
COPY --chown=doom:doom ./scripts $DOOM_HOME/scripts

# the host wrapper (`python scripts/run_tests.py`) re-enters via `docker compose run … tests scripts/run_tests.py …`, which makes docker exec the path directly; the repo commits the script at mode 644, so without +x the container fails to start.
RUN chmod +x $DOOM_HOME/scripts/*.py $DOOM_HOME/scripts/*.sh

# install dev deps for testing (runtime deps already in doombox)
RUN --mount=type=cache,target=/root/.cache/ \
    uv sync --no-install-project --quiet;

USER doom
WORKDIR /home/doom

CMD ["python", "/home/doom/scripts/run_tests.py"]
