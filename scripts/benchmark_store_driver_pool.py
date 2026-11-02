#!/usr/bin/env python3
"""Tenant-scoped PostgreSQL driver/pool benchmark.

The default smoke profile is intended for CI functional checks only.
The controlled profile supports repeated, higher-concurrency measurements,
but the operator must provision and identify a controlled benchmark host.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.util
import json
import math
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

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

PROFILE = os.environ.get("STORE_BENCH_PROFILE", "smoke").lower()
if PROFILE not in {"smoke", "controlled"}:
    raise ValueError("STORE_BENCH_PROFILE must be smoke or controlled")
DEFAULT_CONCURRENCY = "1,8,32" if PROFILE == "smoke" else "1,8,32,64,128"
CONCURRENCY_LEVELS = tuple(
    int(value) for value in os.environ.get(
        "STORE_BENCH_CONCURRENCY_LEVELS", DEFAULT_CONCURRENCY
    ).split(",")
)
ITERATIONS_PER_WORKER = int(os.environ.get(
    "STORE_BENCH_ITERATIONS_PER_WORKER", "20" if PROFILE == "smoke" else "100"
))
REPETITIONS = int(os.environ.get(
    "STORE_BENCH_REPETITIONS", "1" if PROFILE == "smoke" else "5"
))
POOL_MIN = int(os.environ.get("STORE_BENCH_POOL_MIN", "2"))
POOL_MAX = int(os.environ.get("STORE_BENCH_POOL_MAX", "16"))

if not CONCURRENCY_LEVELS or any(x < 1 or x > 512 for x in CONCURRENCY_LEVELS):
    raise ValueError("concurrency levels must be in [1, 512]")
if ITERATIONS_PER_WORKER < 1 or ITERATIONS_PER_WORKER > 10000:
    raise ValueError("iterations per worker must be in [1, 10000]")
if REPETITIONS < 1 or REPETITIONS > 20:
    raise ValueError("repetitions must be in [1, 20]")
if not 1 <= POOL_MIN <= POOL_MAX <= 256:
    raise ValueError("pool bounds must satisfy 1 <= min <= max <= 256")
if PROFILE == "controlled":
    for required in (
        "STORE_BENCH_ENVIRONMENT_ID",
        "STORE_BENCH_RUNNER_CPU_LIMIT",
        "STORE_BENCH_RUNNER_MEMORY_MB",
    ):
        if not os.environ.get(required):
            raise ValueError(f"{required} is required for controlled profile")


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


def summarize(name: str, concurrency: int, repetition: int,
              latencies: list[float], acquire_waits: list[float],
              elapsed: float) -> dict[str, object]:
    return {
        "driver": name,
        "concurrency": concurrency,
        "repetition": repetition,
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
    }


def read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def environment_manifest(dsn: str) -> dict[str, object]:
    cpu_model = None
    cpuinfo = read_text("/proc/cpuinfo")
    if cpuinfo:
        for line in cpuinfo.splitlines():
            if line.lower().startswith(("model name", "hardware")):
                cpu_model = line.split(":", 1)[-1].strip()
                break
    node_version = subprocess.run(
        ["node", "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    with psycopg.connect(dsn, autocommit=True) as conn:
        db = conn.execute(
            """
            SELECT current_setting('server_version') AS server_version,
                   current_setting('max_connections') AS max_connections,
                   current_setting('shared_buffers') AS shared_buffers,
                   current_setting('work_mem') AS work_mem,
                   current_setting('effective_cache_size') AS effective_cache_size,
                   current_setting('track_io_timing') AS track_io_timing
            """
        ).fetchone()
    return {
        "environment_id": os.environ.get("STORE_BENCH_ENVIRONMENT_ID", "github-hosted-runner"),
        "profile": PROFILE,
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "node": node_version,
        "logical_cpu_count": os.cpu_count(),
        "cpu_model": cpu_model,
        "cgroup_v2_cpu_max": read_text("/sys/fs/cgroup/cpu.max"),
        "cgroup_v2_memory_max_bytes": read_text("/sys/fs/cgroup/memory.max"),
        "declared_cpu_limit": os.environ.get("STORE_BENCH_RUNNER_CPU_LIMIT"),
        "declared_memory_limit_mb": os.environ.get("STORE_BENCH_RUNNER_MEMORY_MB"),
        "postgresql": {
            "server_version": db[0],
            "max_connections": db[1],
            "shared_buffers": db[2],
            "work_mem": db[3],
            "effective_cache_size": db[4],
            "track_io_timing": db[5],
        },
    }


def psycopg_sync_case(dsn: str, schema: str, role: str, token: str,
                      concurrency: int, repetition: int) -> dict[str, object]:
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
            "psycopg3-sync+psycopg_pool", concurrency, repetition,
            [x[0] for x in results], [x[1] for x in results], elapsed,
        )
    finally:
        pool.close()


async def psycopg_async_case(dsn: str, schema: str, role: str, token: str,
                             concurrency: int, repetition: int) -> dict[str, object]:
    pool = AsyncConnectionPool(
        conninfo=dsn, min_size=POOL_MIN, max_size=POOL_MAX,
        timeout=10, open=False, kwargs={"prepare_threshold": None},
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
            "psycopg3-async+AsyncConnectionPool", concurrency, repetition,
            [x[0] for x in results], [x[1] for x in results], elapsed,
        )
    finally:
        await pool.close()


async def asyncpg_case(connection_config: dict[str, object], schema: str, role: str,
                       token: str, concurrency: int, repetition: int) -> dict[str, object]:
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
            "asyncpg", concurrency, repetition,
            [x[0] for x in results], [x[1] for x in results], elapsed,
        )
    finally:
        await pool.close()


async def run_async_cases(dsn: str, asyncpg_config: dict[str, object], schema: str,
                          role: str, test_class: object) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for repetition in range(1, REPETITIONS + 1):
        for concurrency in CONCURRENCY_LEVELS:
            token = test_class.issue_assertion(expires_at=int(time.time()) + 120)
            results.append(await psycopg_async_case(
                dsn, schema, role, token, concurrency, repetition
            ))
            token = test_class.issue_assertion(expires_at=int(time.time()) + 120)
            results.append(await asyncpg_case(
                asyncpg_config, schema, role, token, concurrency, repetition
            ))
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
    results: list[dict[str, object]] = []
    try:
        for repetition in range(1, REPETITIONS + 1):
            for concurrency in CONCURRENCY_LEVELS:
                token = test_class.issue_assertion(expires_at=int(time.time()) + 120)
                results.append(psycopg_sync_case(
                    runtime_dsn, fixture.SCHEMA, fixture.RUNTIME_ROLE,
                    token, concurrency, repetition,
                ))

        results.extend(asyncio.run(
            run_async_cases(
                runtime_dsn, asyncpg_config, fixture.SCHEMA,
                fixture.RUNTIME_ROLE, test_class,
            )
        ))

        tokens = {
            f"{repetition}:{concurrency}": test_class.issue_assertion(
                expires_at=int(time.time()) + 120
            )
            for repetition in range(1, REPETITIONS + 1)
            for concurrency in CONCURRENCY_LEVELS
        }
        env_path = os.environ["STORE_BENCH_ENV_FILE"]
        node_output = os.environ["STORE_BENCH_NODE_OUTPUT"]
        Path(env_path).write_text(json.dumps({
            "node_config": {
                key: asyncpg_config[key]
                for key in ("host", "port", "database", "user", "password")
            },
            "schema": fixture.SCHEMA,
            "runtime_role": fixture.RUNTIME_ROLE,
            "tokens": tokens,
            "concurrency_levels": CONCURRENCY_LEVELS,
            "iterations_per_worker": ITERATIONS_PER_WORKER,
            "repetitions": REPETITIONS,
            "pool_min": POOL_MIN,
            "pool_max": POOL_MAX,
        }), encoding="utf-8")
        subprocess.run(
            ["node", str(ROOT / "scripts" / "benchmark_store_driver_pool.mjs")],
            check=True,
            env=os.environ.copy(),
        )
        results.extend(json.loads(Path(node_output).read_text(encoding="utf-8")))
        output = {
            "benchmark_kind": PROFILE,
            "warning": (
                "GitHub-hosted smoke results are not production performance evidence."
                if PROFILE == "smoke"
                else "Controlled profile results are valid only with the recorded environment manifest and repeatability review."
            ),
            "pool": {"min": POOL_MIN, "max": POOL_MAX},
            "prepared_statements": "disabled for portable baseline",
            "concurrency_levels": CONCURRENCY_LEVELS,
            "iterations_per_worker_per_concurrency": ITERATIONS_PER_WORKER,
            "repetitions": REPETITIONS,
            "environment": environment_manifest(runtime_dsn),
            "results": results,
        }
        out_path = os.environ["STORE_BENCH_OUTPUT"]
        Path(out_path).write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps(output, indent=2))
    finally:
        fixture.PostgreSQLTenantEd25519VerifierTests.tearDownClass()


if __name__ == "__main__":
    main()
