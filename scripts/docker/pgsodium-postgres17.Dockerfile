FROM postgres:18.4@sha256:a02db8cac496f15b094798a38254f14d6e00741f709360e5e00bb6668ea31636

ARG PGSODIUM_VERSION=3.1.11
ARG PGSODIUM_SHA256=c8fef093d6d3afe859b03abcf7f598e9fce4298f7bfff283434bc300cba203ab
ARG LIBSODIUM_VERSION=1.0.22
ARG LIBSODIUM_SHA256=adbdd8f16149e81ac6078a03aca6fc03b592b89ef7b5ed83841c086191be3349
ARG PGDG_SERVER_DEV_VERSION=17.11-1.pgdg13+2
ARG PGDG_LIBPQ_DEV_VERSION=18.6-1.pgdg13+2
ARG PGDG_SERVER_DEV_SHA256=a802fd5ec363597ea39b342451803797ef972c684cc2f6a5ffbfab786a75b9f1
ARG PGDG_LIBPQ_DEV_SHA256=b2add61e7fe0e9328140de456a85c96737b517f9cf62b44fd88e86aa2b765f29

RUN set -eux; \
    printf '%s\n' \
      'Types: deb' \
      'URIs: http://snapshot.debian.org/archive/debian/20261027T000000Z' \
      'Suites: trixie trixie-updates' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp' \
      '' \
      'Types: deb' \
      'URIs: http://snapshot.debian.org/archive/debian-security/20261027T000000Z' \
      'Suites: trixie-security' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp' \
      > /etc/apt/sources.list.d/debian.sources; \
    echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99snapshot; \
    apt-get update; \
    cd /tmp; \
    apt-get download \
      "postgresql-server-dev-17=${PGDG_SERVER_DEV_VERSION}" \
      "libpq-dev=${PGDG_LIBPQ_DEV_VERSION}"; \
    echo "${PGDG_SERVER_DEV_SHA256}  postgresql-server-dev-17_${PGDG_SERVER_DEV_VERSION}_amd64.deb" | sha256sum -c -; \
    echo "${PGDG_LIBPQ_DEV_SHA256}  libpq-dev_${PGDG_LIBPQ_DEV_VERSION}_amd64.deb" | sha256sum -c -; \
    apt-get install -y --no-install-recommends \
      build-essential=12.12 \
      ca-certificates=20250419+deb13u1 \
      clang-19=1:19.1.7-3+b1 \
      curl=8.14.1-2+deb13u7 \
      llvm-19-dev=1:19.1.7-3+b1 \
      pkg-config=1.8.1-4 \
      unzip=6.0-29+deb13u1 \
      "./postgresql-server-dev-17_${PGDG_SERVER_DEV_VERSION}_amd64.deb" \
      "./libpq-dev_${PGDG_LIBPQ_DEV_VERSION}_amd64.deb"; \
    curl -fsSL "https://download.libsodium.org/libsodium/releases/libsodium-${LIBSODIUM_VERSION}.tar.gz" \
       -o /tmp/libsodium.tar.gz; \
    echo "${LIBSODIUM_SHA256}  /tmp/libsodium.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/libsodium.tar.gz -C /tmp; \
    cd "/tmp/libsodium-${LIBSODIUM_VERSION}"; \
    ./configure --prefix=/usr/local --libdir=/usr/local/lib; \
    make -j2; \
    make install; \
    ldconfig; \
    curl -fsSL "https://github.com/michelp/pgsodium/releases/download/v${PGSODIUM_VERSION}/pgsodium-${PGSODIUM_VERSION}.zip" \
       -o /tmp/pgsodium.zip; \
    echo "${PGSODIUM_SHA256}  /tmp/pgsodium.zip" | sha256sum -c -; \
    mkdir -p /tmp/pgsodium-src; \
    unzip -q /tmp/pgsodium.zip -d /tmp/pgsodium-src; \
    PGSODIUM_MAKEFILE="$(find /tmp/pgsodium-src -maxdepth 4 -name Makefile -print -quit)"; \
    test -n "$PGSODIUM_MAKEFILE"; \
    cd "$(dirname "$PGSODIUM_MAKEFILE")"; \
    PKG_CONFIG_PATH=/usr/local/lib/pkgconfig make PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config; \
    PKG_CONFIG_PATH=/usr/local/lib/pkgconfig make install PG_CONFIG=/usr/lib/postgresql/17/bin/pg_config; \
    cd /; \
    rm -rf /tmp/libsodium-${LIBSODIUM_VERSION} /tmp/libsodium.tar.gz /tmp/pgsodium-src /tmp/pgsodium.zip \
      /tmp/postgresql-server-dev-17_${PGDG_SERVER_DEV_VERSION}_amd64.deb \
      /tmp/libpq-dev_${PGDG_LIBPQ_DEV_VERSION}_amd64.deb /var/lib/apt/lists/*