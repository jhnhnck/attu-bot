# SPDX-License-Identifier: Apache-2.0
# attu_server | fastapi backend for the spa redesign

FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS server
ENV TZ="America/New_York"
ENV FORCE_COLOR=1
ARG SERVER_HOME="/home/attu"
ENV VIRTUAL_ENV="$SERVER_HOME/.venv"
ENV PATH="$SERVER_HOME/.venv/bin:$PATH"
# attu_server lives at apps/server/attu_server, attu_models at packages/shared-models/attu_models;
# both are workspace virtual packages, so PYTHONPATH carries the import roots.
ENV PYTHONPATH="$SERVER_HOME/apps/server:$SERVER_HOME/packages/shared-models"

WORKDIR $SERVER_HOME/
# the shared .secrets/attu-bot.toml on the host is mode 0660 owned by uid/gid
# 1000 (the same identity the core container runs as). attu keeps its own uid
# for separation but joins gid 1000 so the read-only mount is readable.
RUN groupadd --gid 1000 hostsecrets; \
    useradd --home-dir /home/attu --uid 1100 --groups hostsecrets attu; \
    mkdir -p $SERVER_HOME; \
    chown -Rc attu:attu $SERVER_HOME

# minimal system deps; curl for the healthcheck only
RUN --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    set -eux; \
    apt-get update -qq; \
    apt-get install -qq curl

USER attu

# workspace manifests + lockfile (need every member's pyproject for uv sync to resolve)
COPY --chown=attu:attu ./pyproject.toml ./uv.lock $SERVER_HOME/
COPY --chown=attu:attu ./apps/bot/pyproject.toml $SERVER_HOME/apps/bot/pyproject.toml
COPY --chown=attu:attu ./apps/server/pyproject.toml $SERVER_HOME/apps/server/pyproject.toml
COPY --chown=attu:attu ./packages/shared-models/pyproject.toml $SERVER_HOME/packages/shared-models/pyproject.toml
# attu-logging and attu-wiki are package = false, so only their manifests are
# needed; uv still requires every workspace member present to resolve at all
COPY --chown=attu:attu ./packages/attu-logging/pyproject.toml $SERVER_HOME/packages/attu-logging/pyproject.toml
COPY --chown=attu:attu ./packages/attu-wiki/pyproject.toml $SERVER_HOME/packages/attu-wiki/pyproject.toml

# install only the server's dep tree
RUN --mount=type=cache,target=$SERVER_HOME/.cache/,uid=1100,gid=1100 \
    uv venv && uv sync --no-install-project --no-dev --package attu-server --quiet

# include only what the server needs
COPY --chown=attu:attu ./LICENSE ./README.md $SERVER_HOME/
COPY --chown=attu:attu ./apps/server/attu_server $SERVER_HOME/apps/server/attu_server
COPY --chown=attu:attu ./packages/shared-models/attu_models $SERVER_HOME/packages/shared-models/attu_models

EXPOSE 5000
CMD ["uvicorn", "attu_server.main:app", "--host", "0.0.0.0", "--port", "5000"]
