#!/usr/bin/env python3
"""CI smoke benchmark for Store-like tenant-scoped PostgreSQL transactions.

This is a functional/relative smoke test on an ephemeral runner, not a
production performance ranking. It reuses the Ed25519 verifier fixture.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.util
import json
import math
import os
import statistics
import subprocess
import sys
import time
from urllib.parse import urlsplit
from pathlib import Path

import asyncpg
import psycopg
from psycopg.conninfo import make_conninfo
from psycopg_pool import AsyncConnectionPool, ConnectionPool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "tenant_ed25519_fixture",
    ROOT / "scripts" / "test_postgres_tenant_ed25519_verifier.py",
)
fixture = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(fixture)

CONCURRENCY_LEVELS = (1, 8, 32)
ITERATIONS_PER_WORKER = 20
POOL_MIN = 2
POOL_MAX = 16


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


def summarize(name: str, concurrency: int, latencies: list[float],
              acquire_waits: list[float], elapsed: float) -> dict[str, object]:
    return {
        "driver": name,
        "concurrency": concurrency,
        "operations": len(latencies),
        "throughput_ops_per_second": round(len(latencies) / elapsed, 2),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50) * 1000, 3),
            "p95": round(percentile(latencies, 0.95) * 1000, 3),
            "p99": round(percentile(latencies, 0.99) * 1000, 3),
        },
        "pool_acquire_wait_ms": {
            "p50": round(percentile(acquire_waits, 0.50) * 1000, 3),
            "p95": round(percentile(acquire_waits, 0.95) * 1000, 3),
            "p99": round(percentile(acquire_waits, 0.99) * 1000, 3),
        },
        "environment": "GitHub-hosted ephemeral runner; smoke only",
    }


def psycopg_sync_case(dsn: str, schema: str, role: str, token: str,
                      concurrency: int) -> dict[str, object]:
    pool = ConnectionPool(
        conninfo=dsn, min_size=POOL_MIN, max_size=POOL_MAX,
        timeout=10, open=False, kwargs={"prepare_threshold": None},
    )
    pool.open(wait=True, timeout=30)

    def operation() -> tuple[float, float]:
        started = time.perf_counter()
        with pool.connection(timeout=10) as conn:
            acquired = time.perf_counter()
            conn.execute(f'SET LOCAL ROLE "{role}"')
            conn.execute(
                "SELECT set_config(%s, %s, true)",
                ("app.tenant_assertion", token),
            )
            rows = conn.execute(
                f'SELECT row_id FROM "{schema}".tenant_rows WHERE row_id=%s',
                ("a1",),
            ).fetchall()
            if rows != [("a1",)]:
                raise AssertionError(f"unexpected RLS rows: {rows!r}")
        ended = time.perf_counter()
        return ended - started, acquired - started

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            list(executor.map(lambda _: operation(), range(10)))
            count = concurrency * ITERATIONS_PER_WORKER
            started = time.perf_counter()
            results = list(executor.map(lambda _: operation(), range(count)))
            elapsed = time.perf_counter() - started
        return summarize(
            "psycopg3-sync+psycopg_pool", concurrency,
            [x[0] for x in results], [x[1] for x in results], elapsed,
        )
    finally:
        pool.close()


async def psycopg_async_case(dsn: str, schema: str, role: str, token: str,
                             concurrency: int) -> dict[str, object]:
    pool = AsyncConnectionPool(
        conninfo=dsn, min_size=POOL_MIN, max_size=POOL_MAX,
        timeout=10, open=False,
    )
    await pool.open(wait=True, timeout=30)

    async def operation() -> tuple[float, float]:
        started = time.perf_counter()
        async with pool.connection(timeout=10) as conn:
            acquired = time.perf_counter()
            await conn.execute(f'SET LOCAL ROLE "{role}"')
            await conn.execute(
                "SELECT set_config(%s, %s, true)",
                ("app.tenant_assertion", token),
            )
            cur = await conn.execute(
                f'SELECT row_id FROM "{schema}".tenant_rows WHERE row_id=%s',
                ("a1",),
            )
            rows = await cur.fetchall()
            if rows != [("a1",)]:
                raise AssertionError(f"unexpected RLS rows: {rows!r}")
        ended = time.perf_counter()
        return ended - started, acquired - started

    try:
        await asyncio.gather(*(operation() for _ in range(10)))
        count = concurrency * ITERATIONS_PER_WORKER
        semaphore = asyncio.Semaphore(concurrency)

        async def bounded_operation():
            async with semaphore:
                return await operation()

        started = time.perf_counter()
        results = await asyncio.gather(*(bounded_operation() for _ in range(count)))
        elapsed = time.perf_counter() - started
        return summarize(
            "psycopg3-async+AsyncConnectionPool", concurrency,
            [x[0] for x in results], [x[1] for x in results], elapsed,
        )
    finally:
        await pool.close()


async def asyncpg_case(connection_config: dict[str, object], schema: str, role: str, token: str,
                       concurrency: int) -> dict[str, object]:
    pool = await asyncpg.create_pool(
        **connection_config, min_size=POOL_MIN, max_size=POOL_MAX,
        command_timeout=10,
    )

    async def operation() -> tuple[float, float]:
        started = time.perf_counter()
        async with pool.acquire(timeout=10) as conn:
            acquired = time.perf_counter()
            async with conn.transaction():
                await conn.execute(f'SET LOCAL ROLE "{role}"')
                await conn.execute(
                    "SELECT set_config('app.tenant_assertion', $1, true)",
                    token,
                )
                rows = await conn.fetch(
                    f'SELECT row_id FROM "{schema}".tenant_rows WHERE row_id=$1',
                    "a1",
                )
                if [row["row_id"] for row in rows] != ["a1"]:
                    raise AssertionError(f"unexpected RLS rows: {rows!r}")
        ended = time.perf_counter()
        return ended - started, acquired - started

    try:
        await asyncio.gather(*(operation() for _ in range(10)))
        count = concurrency * ITERATIONS_PER_WORKER
        semaphore = asyncio.Semaphore(concurrency)

        async def bounded_operation():
            async with semaphore:
                return await operation()

        started = time.perf_counter()
        results = await asyncio.gather(*(bounded_operation() for _ in range(count)))
        elapsed = time.perf_counter() - started
        return summarize(
            "asyncpg", concurrency,
            [x[0] for x in results], [x[1] for x in results], elapsed,
        )
    finally:
        await pool.close()


async def run_async_cases(dsn: str, asyncpg_config: dict[str, object], schema: str, role: str, token: str) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for concurrency in CONCURRENCY_LEVELS:
        results.append(await psycopg_async_case(dsn, schema, role, token, concurrency))
        results.append(await asyncpg_case(asyncpg_config, schema, role, token, concurrency))
    return results


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    fixture.PostgreSQLTenantEd25519VerifierTests.setUpClass()
    test_class = fixture.PostgreSQLTenantEd25519VerifierTests
    runtime_dsn = make_conninfo(
        database_url,
        user=fixture.LOGIN_ROLE,
        password=fixture.LOGIN_PASSWORD,
    )
    parsed = urlsplit(database_url)
    asyncpg_config = {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/") or "stemlab_test",
        "user": fixture.LOGIN_ROLE,
        "password": fixture.LOGIN_PASSWORD,
        "statement_cache_size": 0,
    }
    token = test_class.issue_assertion(expires_at=int(time.time()) + 120)
    results: list[dict[str, object]] = []
    try:
        for concurrency in CONCURRENCY_LEVELS:
            results.append(
                psycopg_sync_case(
                    runtime_dsn, fixture.SCHEMA, fixture.RUNTIME_ROLE,
                    token, concurrency,
                )
            )
        results.extend(asyncio.run(
            run_async_cases(
                runtime_dsn, asyncpg_config, fixture.SCHEMA, fixture.RUNTIME_ROLE, token
            )
        ))

        env_path = os.environ["STORE_BENCH_ENV_FILE"]
        node_output = os.environ["STORE_BENCH_NODE_OUTPUT"]
        Path(env_path).write_text(json.dumps({
            "node_config": {
                key: asyncpg_config[key]
                for key in ("host", "port", "database", "user", "password")
            },
            "schema": fixture.SCHEMA,
            "runtime_role": fixture.RUNTIME_ROLE,
            "token": token,
        }), encoding="utf-8")
        subprocess.run(
            ["node", str(ROOT / "scripts" / "benchmark_store_driver_pool.mjs")],
            check=True,
            env=os.environ.copy(),
        )
        results.extend(json.loads(Path(node_output).read_text(encoding="utf-8")))
        output = {
            "benchmark_kind": "smoke",
            "warning": "GitHub-hosted runner results are not production performance evidence.",
            "postgresql": "17.11",
            "rls": "pgsodium Ed25519 verifier enabled",
            "pool": {"min": POOL_MIN, "max": POOL_MAX},
            "prepared_statements": "disabled for portable baseline",
            "iterations_per_worker_per_concurrency": ITERATIONS_PER_WORKER,
            "results": results,
        }
        out_path = os.environ["STORE_BENCH_OUTPUT"]
        Path(out_path).write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps(output, indent=2))
    finally:
        fixture.PostgreSQLTenantEd25519VerifierTests.tearDownClass()


if __name__ == "__main__":
    main()
