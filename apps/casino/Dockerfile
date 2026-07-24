# casino-bot container — system deps, application code, and Python packages
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS casinobox
ENV TZ="America/New_York"
ENV FORCE_COLOR=1
ARG CASINO_HOME="/home/casino"
ENV VIRTUAL_ENV="$CASINO_HOME/.venv"
ENV PATH="$CASINO_HOME/.venv/bin:$PATH"
# nova_core lives at apps/bot/nova_core; casino_bot at apps/casino; attu_models at packages/shared-models;
# all are workspace virtual packages (uv does not install them), so PYTHONPATH carries the import roots.
ENV PYTHONPATH="$CASINO_HOME/apps/bot:$CASINO_HOME/apps/casino:$CASINO_HOME/packages/shared-models:$CASINO_HOME/packages/attu-logging"

# setup runtime
RUN mkdir -p $CASINO_HOME/
WORKDIR $CASINO_HOME/
RUN useradd --home-dir /home/casino --uid 1000 casino; \
    chown -Rc casino:casino /home/casino;

USER casino

# workspace manifests and lockfile (need every member's pyproject for uv sync to resolve)
COPY --chown=casino:casino ./pyproject.toml ./uv.lock $CASINO_HOME/
COPY --chown=casino:casino ./apps/bot/pyproject.toml $CASINO_HOME/apps/bot/pyproject.toml
COPY --chown=casino:casino ./apps/casino/pyproject.toml $CASINO_HOME/apps/casino/pyproject.toml
COPY --chown=casino:casino ./apps/server/pyproject.toml $CASINO_HOME/apps/server/pyproject.toml
COPY --chown=casino:casino ./packages/shared-models/pyproject.toml $CASINO_HOME/packages/shared-models/pyproject.toml
COPY --chown=casino:casino ./packages/attu-logging/pyproject.toml $CASINO_HOME/packages/attu-logging/pyproject.toml

# install all service dependencies
RUN --mount=type=cache,target=$CASINO_HOME/.cache/,uid=1000,gid=1000 \
    uv venv && uv sync --no-install-project --no-dev --quiet;

# include docs/license with code
COPY --chown=casino:casino ./LICENSE ./README.md $CASINO_HOME/
COPY --chown=casino:casino ./apps/casino/casino-bot.py $CASINO_HOME/apps/casino/casino-bot.py
COPY --chown=casino:casino ./apps/casino/casino_bot $CASINO_HOME/apps/casino/casino_bot
COPY --chown=casino:casino ./apps/bot/nova_core $CASINO_HOME/apps/bot/nova_core
COPY --chown=casino:casino ./packages/shared-models/attu_models $CASINO_HOME/packages/shared-models/attu_models
COPY --chown=casino:casino ./packages/attu-logging/attu_logging $CASINO_HOME/packages/attu-logging/attu_logging

CMD ["python", "-u", "/home/casino/apps/casino/casino-bot.py", "bot"]
