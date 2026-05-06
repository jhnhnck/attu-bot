# attu-chat container - dormant until apps/chat/compose.yml is included from root
# mirrors apps/bot/Dockerfile so revival is a `docker compose build` away.
FROM ghcr.io/astral-sh/uv:python3.13-trixie AS attu-chat
ENV TZ="America/New_York"
ENV FORCE_COLOR=1
ARG DOOM_HOME="/home/doom"
ENV VIRTUAL_ENV="$DOOM_HOME/.venv"
ENV PATH="$DOOM_HOME/.venv/bin:$PATH"
# attu_chat lives at apps/chat/attu_chat; cross-app imports against doom_bot.* (logging,
# tasks, client.core) need apps/bot on the path while chat reuses bot infra.
ENV PYTHONPATH="$DOOM_HOME/apps/chat:$DOOM_HOME/apps/bot:$DOOM_HOME/packages/shared-models"

RUN mkdir -p $DOOM_HOME/
WORKDIR $DOOM_HOME/
RUN useradd --home-dir /home/doom --uid 1000 doom; \
    chown -Rc doom:doom /home/doom;

RUN --mount=type=cache,target=/var/lib/apt \
    set -eux; \
    apt-get update -qq; \
    apt-get install -qq curl;

SHELL [ "/bin/bash", "-euc" ]
USER doom

COPY --chown=doom:doom ./pyproject.toml ./uv.lock $DOOM_HOME/
COPY --chown=doom:doom ./apps/bot/pyproject.toml $DOOM_HOME/apps/bot/pyproject.toml
COPY --chown=doom:doom ./apps/chat/pyproject.toml $DOOM_HOME/apps/chat/pyproject.toml
COPY --chown=doom:doom ./apps/server/pyproject.toml $DOOM_HOME/apps/server/pyproject.toml
COPY --chown=doom:doom ./packages/shared-models/pyproject.toml $DOOM_HOME/packages/shared-models/pyproject.toml

RUN --mount=type=cache,target=$DOOM_HOME/.cache/,uid=1000,gid=1000 \
    uv venv && uv sync --no-install-project --no-dev --quiet;

COPY --chown=doom:doom ./LICENSE ./README.md $DOOM_HOME/
COPY --chown=doom:doom ./apps/chat/attu-chat.py $DOOM_HOME/apps/chat/attu-chat.py
COPY --chown=doom:doom ./apps/chat/attu_chat $DOOM_HOME/apps/chat/attu_chat
COPY --chown=doom:doom ./apps/chat/assets $DOOM_HOME/apps/chat/assets
COPY --chown=doom:doom ./apps/chat/legacy_web $DOOM_HOME/apps/chat/legacy_web
COPY --chown=doom:doom ./apps/bot/doom_bot $DOOM_HOME/apps/bot/doom_bot
COPY --chown=doom:doom ./packages/shared-models/attu_models $DOOM_HOME/packages/shared-models/attu_models
