FROM postgres:17.11@sha256:0b81cec82228160abfa753aeaad0609b709eb26eeb950f2e404ad2326e1cc370

ARG PGSODIUM_VERSION=3.1.11
ARG PGSODIUM_SHA256=c8fef093d6d3afe859b03abcf7f598e9fce4298f7bfff283434bc300cba203ab
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
    && curl -fsSL "https://github.com/michelp/pgsodium/releases/download/v${PGSODIUM_VERSION}/pgsodium-${PGSODIUM_VERSION}.zip" \
       -o /tmp/pgsodium.zip \
    && echo "${PGSODIUM_SHA256}  /tmp/pgsodium.zip" | sha256sum -c - \
    && mkdir -p /tmp/pgsodium-src \
    && unzip -q /tmp/pgsodium.zip -d /tmp/pgsodium-src \
    && PGSODIUM_MAKEFILE="$(find /tmp/pgsodium-src -maxdepth 4 -name Makefile -print -quit)" \
    && test -n "$PGSODIUM_MAKEFILE" \
    && cd "$(dirname "$PGSODIUM_MAKEFILE")" \
    && PKG_CONFIG_PATH=/usr/local/lib/pkgconfig make PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config \
    && PKG_CONFIG_PATH=/usr/local/lib/pkgconfig make install PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config \
    && cd / \
    && rm -rf /tmp/libsodium-${LIBSODIUM_VERSION} /tmp/libsodium.tar.gz /tmp/pgsodium-src /tmp/pgsodium.zip /var/lib/apt/lists/*
