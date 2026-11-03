#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import threading
import uuid

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
DSN = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stemlab_test")
SCHEMA = "receipt_v2alpha2_" + uuid.uuid4().hex[:12]
SQL = (ROOT / "sql/request-receipt-v2alpha2.sql").read_text().replace("__SCHEMA__", SCHEMA)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def reserve(conn, key: str, operation_id: str, digest: str = DIGEST_A):
    return conn.execute(
        f"SELECT * FROM {SCHEMA}.reserve_request_receipt_v2alpha2(%s,%s,%s,%s,%s,%s,%s)",
        ("tenant-a", "worker.job.complete", key, operation_id, digest, "job", "job-1"),
    ).fetchone()


def expect_error(conn, sql: str, params: tuple, expected: str) -> None:
    try:
        conn.execute(sql, params)
    except psycopg.Error as exc:
        assert expected in str(exc), f"expected {expected}, got {exc!r}"
    else:
        raise AssertionError(f"expected database rejection: {expected}")


def main() -> None:
    conn = psycopg.connect(DSN, autocommit=True)
    try:
        conn.execute(SQL)
        reserve_sql = f"SELECT * FROM {SCHEMA}.reserve_request_receipt_v2alpha2(%s,%s,%s,%s,%s,%s,%s)"

        first = reserve(conn, "key-replay", "operation-1")
        assert first[1] is True and first[2] == "pending" and first[3] == DIGEST_A
        finalized = conn.execute(
            f"SELECT * FROM {SCHEMA}.finalize_request_receipt_v2alpha2(%s,%s,%s::jsonb)",
            (first[0], "succeeded", json.dumps({"result_ref": "artifact:stable"})),
        ).fetchone()
        assert finalized[1] == "succeeded"

        replay = reserve(conn, "key-replay", "operation-retry")
        assert replay[0] == first[0] and replay[1] is False
        assert replay[2] == "succeeded" and replay[4] == "operation-1"
        assert replay[5] == {"result_ref": "artifact:stable"}

        expect_error(
            conn, reserve_sql,
            ("tenant-a", "worker.job.complete", "key-replay", "operation-other",
             DIGEST_B, "job", "job-1"),
            "IDEMPOTENCY_CONFLICT",
        )
        expect_error(
            conn, reserve_sql,
            ("tenant-a", "worker.job.complete", "key-new", "operation-1",
             DIGEST_A, "job", "job-1"),
            "OPERATION_ID_CONFLICT",
        )

        # Same finalization is idempotent; a conflicting terminal result is not.
        same_finalize = conn.execute(
            f"SELECT * FROM {SCHEMA}.finalize_request_receipt_v2alpha2(%s,%s,%s::jsonb)",
            (first[0], "succeeded", json.dumps({"result_ref": "artifact:stable"})),
        ).fetchone()
        assert same_finalize[1] == "succeeded"
        expect_error(
            conn,
            f"SELECT * FROM {SCHEMA}.finalize_request_receipt_v2alpha2(%s,%s,%s::jsonb)",
            (first[0], "failed", json.dumps({"error": "different"})),
            "RECEIPT_ALREADY_FINALIZED",
        )

        # Competing first submissions serialize on the unique idempotency key.
        barrier = threading.Barrier(2)
        def contender(op_id: str):
            with psycopg.connect(DSN, autocommit=True) as c:
                barrier.wait(timeout=10)
                return reserve(c, "key-race", op_id)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(contender, ("operation-race-a", "operation-race-b")))
        assert sorted(bool(row[1]) for row in outcomes) == [False, True], outcomes
        assert outcomes[0][0] == outcomes[1][0], outcomes
        assert outcomes[0][3] == outcomes[1][3] == DIGEST_A
        count = conn.execute(
            f"SELECT count(*) FROM {SCHEMA}.request_receipts_v2alpha2 WHERE tenant_id='tenant-a' AND action='worker.job.complete' AND idempotency_key='key-race'"
        ).fetchone()[0]
        assert count == 1, f"concurrent first use created {count} Receipts"

        # A surrounding transaction rollback removes the reservation.
        conn.execute("BEGIN")
        rolled_back = reserve(conn, "key-rollback", "operation-rollback")
        assert rolled_back[1] is True
        conn.execute("ROLLBACK")
        remaining = conn.execute(
            f"SELECT count(*) FROM {SCHEMA}.request_receipts_v2alpha2 WHERE idempotency_key='key-rollback'"
        ).fetchone()[0]
        assert remaining == 0

        print("Receipt same-key/same-digest replay returns original receipt and outcome: PASS")
        print("Receipt same-key/different-digest deterministic conflict: PASS")
        print("Receipt operation_id uniqueness: PASS")
        print("Receipt terminal finalization idempotency and conflict: PASS")
        print("Receipt concurrent first-use arbitration (two connections): PASS")
        print("Receipt outer transaction rollback: PASS")
    finally:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.close()


if __name__ == "__main__":
    main()
