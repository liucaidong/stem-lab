FROM postgres:17.11

ARG PGSODIUM_VERSION=3.1.11
ARG LIBSODIUM_VERSION=1.0.22
ARG LIBSODIUM_SHA256=adbdd8f16149e81ac6078a03aca6fc03b592b89ef7b5ed83841c086191be3349

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       ca-certificates \
       curl \
       pkg-config \
       postgresql-server-dev-17 \
       unzip \
    && curl -fsSL "https://download.libsodium.org/libsodium/releases/libsodium-${LIBSODIUM_VERSION}.tar.gz" \
       -o /tmp/libsodium.tar.gz \
    && echo "${LIBSODIUM_SHA256}  /tmp/libsodium.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/libsodium.tar.gz -C /tmp \
    && cd "/tmp/libsodium-${LIBSODIUM_VERSION}" \
    && ./configure --prefix=/usr/local --libdir=/usr/local/lib \
    && make -j2 \
    && make install \
    && ldconfig \
    && curl -fsSL "https://api.pgxn.org/dist/pgsodium/${PGSODIUM_VERSION}/pgsodium-${PGSODIUM_VERSION}.zip" \
       -o /tmp/pgsodium.zip \
    && mkdir -p /tmp/pgsodium-src \
    && unzip -q /tmp/pgsodium.zip -d /tmp/pgsodium-src \
    && PGSODIUM_MAKEFILE="$(find /tmp/pgsodium-src -maxdepth 4 -name Makefile -print -quit)" \
    && test -n "$PGSODIUM_MAKEFILE" \
    && cd "$(dirname "$PGSODIUM_MAKEFILE")" \
    && PKG_CONFIG_PATH=/usr/local/lib/pkgconfig make PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config \
    && PKG_CONFIG_PATH=/usr/local/lib/pkgconfig make install PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config \
    && cd / \
    && rm -rf /tmp/libsodium-${LIBSODIUM_VERSION} /tmp/libsodium.tar.gz /tmp/pgsodium-src /tmp/pgsodium.zip /var/lib/apt/lists/*
