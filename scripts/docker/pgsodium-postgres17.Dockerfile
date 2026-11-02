FROM postgres:17

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
    && cd /tmp/pgsodium-src \
    && make \
    && make install \
    && cd / \
    && rm -rf /tmp/pgsodium-src /tmp/pgsodium.zip /var/lib/apt/lists/*
