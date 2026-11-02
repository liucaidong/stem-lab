#!/usr/bin/env python3
"""Real PostgreSQL demonstration of GUC spoofability and transaction cleanup.

A passing spoof test is an expected vulnerability reproduction: plain custom
GUC is caller-controlled and must not be treated as a trusted identity.
"""
from __future__ import annotations

import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg

DSN = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stemlab_test")
SUFFIX = uuid.uuid4().hex[:10]
SCHEMA = "tenant_boundary_" + SUFFIX
ROLE = "tenant_ctx_" + SUFFIX


class TenantRlsTrustBoundaryPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = psycopg.connect(DSN, autocommit=True)
        cls.admin.execute(
            f"CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        cls.admin.execute(f"CREATE SCHEMA {SCHEMA}")
        cls.admin.execute(
            f"CREATE TABLE {SCHEMA}.tenant_rows "
            "(tenant_id text NOT NULL, row_id text NOT NULL, value text NOT NULL, "
            "PRIMARY KEY (tenant_id,row_id))"
        )
        cls.admin.execute(
            f"INSERT INTO {SCHEMA}.tenant_rows VALUES "
            "('tenant-a','a1','A secret'),('tenant-b','b1','B secret')"
        )
        cls.admin.execute(
            f"ALTER TABLE {SCHEMA}.tenant_rows ENABLE ROW LEVEL SECURITY"
        )
        cls.admin.execute(
            f"ALTER TABLE {SCHEMA}.tenant_rows FORCE ROW LEVEL SECURITY"
        )
        cls.admin.execute(
            f"CREATE POLICY tenant_scope ON {SCHEMA}.tenant_rows "
            "USING (tenant_id=current_setting('app.tenant_id',true)) "
            "WITH CHECK (tenant_id=current_setting('app.tenant_id',true))"
        )
        cls.admin.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {ROLE}")
        cls.admin.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON {SCHEMA}.tenant_rows TO {ROLE}")

    @classmethod
    def tearDownClass(cls):
        cls.admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cls.admin.execute(f"DROP ROLE IF EXISTS {ROLE}")
        cls.admin.close()

    def connect(self):
        conn = psycopg.connect(DSN, autocommit=True)
        conn.execute(f"SET ROLE {ROLE}")
        conn.execute(f"SET search_path TO {SCHEMA}, public")
        return connonn

    def test_missing_context_fails_closed(self):
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM tenant_rows").fetchone()[0], 0)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute("INSERT INTO tenant_rows VALUES ('tenant-a','blocked','x')")

    def test_plain_guc_can_be_spoofed_by_application_role_expected_vulnerability(self):
        with self.connect() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id','tenant-a',true)")
                self.assertEqual(conn.execute("SELECT value FROM tenant_rows").fetchall(), [("A secret",)])
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id','tenant-b',true)")
                # This proves GUC-only RLS does not authenticate tenant identity.
                self.assertEqual(conn.execute("SELECT value FROM tenant_rows").fetchall(), [("B secret",)])

    def test_transaction_local_context_clears_after_commit_on_reused_connection(self):
        with self.connect() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id','tenant-a',true)")
                self.assertEqual(conn.execute("SELECT count(*) FROM tenant_rows").fetchone()[0], 1)
            with conn.transaction():
                self.assertEqual(conn.execute("SELECT count(*) FROM tenant_rows").fetchone()[0], 0)

    def test_transaction_local_context_clears_after_rollback(self):
        with self.connect() as conn:
            try:
                with conn.transaction():
                    conn.execute("SELECT set_config('app.tenant_id','tenant-a',true)")
                    raise RuntimeError("injected rollback")
            except RuntimeError:
                pass
            with conn.transaction():
                self.assertEqual(conn.execute("SELECT count(*) FROM tenant_rows").fetchone()[0], 0)

    def test_concurrent_tenant_transactions_do_not_cross_read(self):
        barrier = threading.Barrier(2)

        def read(tenant):
            with self.connect() as conn:
                barrier.wait()
                with conn.transaction():
                    conn.execute("SELECT set_config('app.tenant_id',%s,true)", (tenant,))
                    return conn.execute("SELECT tenant_id FROM tenant_rows ORDER BY tenant_id").fetchall()

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(read, "tenant-a")
            b = pool.submit(read, "tenant-b")
            self.assertEqual(a.result(), [("tenant-a",)])
            self.assertEqual(b.result(), [("tenant-b",)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
