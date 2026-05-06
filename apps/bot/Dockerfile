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
ENV PYTHONPATH="$DOOM_HOME/apps/bot:$DOOM_HOME/packages/shared-models"

# setup runtime
RUN mkdir -p $DOOM_HOME/
WORKDIR $DOOM_HOME/
RUN useradd --home-dir /home/doom --uid 1000 doom; \
    chown -Rc doom:doom /home/doom;

# install system dependencies
RUN --mount=type=cache,target=/var/lib/apt \
    set -eux; \
    apt-get update -qq; \
    apt-get install -qq \
    curl \
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
COPY --chown=doom:doom ./apps/chat/pyproject.toml $DOOM_HOME/apps/chat/pyproject.toml
COPY --chown=doom:doom ./apps/server/pyproject.toml $DOOM_HOME/apps/server/pyproject.toml
COPY --chown=doom:doom ./packages/shared-models/pyproject.toml $DOOM_HOME/packages/shared-models/pyproject.toml

# install all service dependencies
RUN --mount=type=cache,target=$DOOM_HOME/.cache/,uid=1000,gid=1000 \
    uv venv && uv sync --no-install-project --no-dev --quiet;

# include docs/license with code
COPY --chown=doom:doom ./LICENSE ./README.md $DOOM_HOME/
COPY --chown=doom:doom ./apps/bot/doom-bot.py $DOOM_HOME/apps/bot/doom-bot.py
COPY --chown=doom:doom ./apps/bot/doom_bot $DOOM_HOME/apps/bot/doom_bot
COPY --chown=doom:doom ./apps/bot/legacy_web $DOOM_HOME/apps/bot/legacy_web
COPY --chown=doom:doom ./apps/bot/assets/hatch.toml $DOOM_HOME/apps/bot/assets/hatch.toml
COPY --chown=doom:doom ./apps/bot/assets/static $DOOM_HOME/apps/bot/assets/static
COPY --chown=doom:doom ./packages/shared-models/attu_models $DOOM_HOME/packages/shared-models/attu_models

# stamp version and build time into __init__.py from git-info stage
COPY --from=git-info --chown=doom:doom /src/apps/bot/doom_bot/__init__.py $DOOM_HOME/apps/bot/doom_bot/__init__.py

# --- for running tests inside docker ---
FROM doombox AS tester
USER root

# Install Node.js for JavaScript tests
# repeat TODO: hardcoded version; keep updated
RUN --mount=type=cache,target=/var/lib/apt \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /usr/share/keyrings/nodesource.gpg; \
    printf 'Types: deb\nURIs: https://deb.nodesource.com/node_22.x\nSuites: nodistro\nComponents: main\nArchitectures: amd64\nSigned-By: /usr/share/keyrings/nodesource.gpg\n' > /etc/apt/sources.list.d/nodesource.sources; \
    apt-get update -qq; \
    apt-get install -qq nsolid;

# copy extra needed files (as root so scripts can be chmod'd)
COPY --chown=doom:doom \
    ./package.json \
    ./eslint.config.js \
    ./vitest.config.js \
    $DOOM_HOME/

COPY --chown=doom:doom ./tests $DOOM_HOME/tests
COPY --chown=doom:doom ./scripts $DOOM_HOME/scripts

# install dev deps for testing (runtime deps already in doombox)
RUN --mount=type=cache,target=/root/.cache/ \
    uv sync --no-install-project --quiet; \
    chmod a+x "$DOOM_HOME/scripts/run_tests.py";

USER doom
WORKDIR /home/doom

# Install npm dependencies
RUN npm install > /dev/null;

CMD ["python", "/home/doom/scripts/run_tests.py"]
