FROM postgres:17.11

ARG PGSODIUM_VERSION=3.1.11

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       ca-certificates \
       curl \
       libsodium-dev \
       postgresql-server-dev-17 \
       unzip \
    && curl -fsSL "https://api.pgxn.org/dist/pgsodium/${PGSODIUM_VERSION}/pgsodium-${PGSODIUM_VERSION}.zip" \
       -o /tmp/pgsodium.zip \
    && mkdir -p /tmp/pgsodium-src \
    && unzip -q /tmp/pgsodium.zip -d /tmp/pgsodium-src \
    && PGSODIUM_MAKEFILE="$(find /tmp/pgsodium-src -maxdepth 4 -name Makefile -print -quit)" \
    && test -n "$PGSODIUM_MAKEFILE" \
    && cd "$(dirname "$PGSODIUM_MAKEFILE")" \
    && make PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config \
    && make install PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config \
    && cd / \
    && rm -rf /tmp/pgsodium-src /tmp/pgsodium.zip /var/lib/apt/lists/*
