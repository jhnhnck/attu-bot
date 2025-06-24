FROM rust:bookworm AS builder
RUN cargo install --version ^0.45 resvg

FROM python:3.13-bookworm
ENV TZ="America/New_York"
ENV FORCE_COLOR=1

# copy files and install deps
RUN mkdir /app
WORKDIR /app
COPY ./requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# install resvg
COPY --from=builder /usr/local/cargo/bin/resvg /usr/local/bin/resvg

# add runtime user and change perms
RUN set -eux; \
    useradd --home-dir /app --uid 1000 doom; \
    chown -Rc doom:doom /app;

RUN printf 'BUILD_TIME="%s"\n' "$(date)" >> /app/.env
