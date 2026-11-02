#!/usr/bin/env python3
"""PostgreSQL-side HMAC assertion verification in the R03.52.7.1 spike.

The issuer key is shared with this disposable test harness only. The database
runtime role never receives key-table access or verifier ownership. This is
not a production key-custody or asymmetric-signature implementation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import unittest
import uuid

import psycopg
from psycopg.conninfo import make_conninfo

DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/stemlab_test",
)
SUFFIX = uuid.uuid4().hex[:10]
SCHEMA = "tenant_verifier_" + SUFFIX
RUNTIME_ROLE = "tenant_runtime_" + SUFFIX
VERIFIER_ROLE = "tenant_verifier_owner_" + SUFFIX
LOGIN_ROLE = "tenant_login_" + SUFFIX
LOGIN_PASSWORD = uuid.uuid4().hex + uuid.uuid4().hex
ISSUER_KEY = os.urandom(32)
AUDIENCE = "stemlab-api"
MAX_LIFETIME_SECONDS = 120


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def issue_assertion(
    *,
    tenant_id: str = "tenant-a",
    subject: str = "user-1",
    audience: str = AUDIENCE,
    action: str = "read",
    resource_id: str = "a1",
    issued_at: int | None = None,
    expires_at: int | None = None,
    nonce: str = "nonce-1",
    key: bytes = ISSUER_KEY,
) -> str:
    import time

    now = int(time.time())
    payload = {
        "v": 1,
        "tenant_id": tenant_id,
        "sub": subject,
        "aud": audience,
        "action": action,
        "resource_id": resource_id,
        "iat": now if issued_at is None else issued_at,
        "exp": now + 60 if expires_at is None else expires_at,
        "nonce": nonce,
    }
    encoded = b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(key, encoded.encode("ascii"), hashlib.sha256).digest()
    return encoded + "." + b64url(signature)


def tamper_signature(token: str) -> str:
    payload_part, signature_part = token.split(".")
    signature = bytearray(base64.urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4)))
    signature[0] ^= 0x01
    return payload_part + "." + b64url(bytes(signature))


def tamper_payload_without_resigning(token: str, **changes: object) -> str:
    payload_part, signature_part = token.split(".")
    raw = base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4))
    payload = json.loads(raw)
    payload.update(changes)
    changed = b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return changed + "." + signature_part


class PostgreSQLTenantAssertionVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.admin = psycopg.connect(DSN, autocommit=True)
        cls.admin.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        cls.admin.execute(
            f"CREATE ROLE {VERIFIER_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        cls.admin.execute(
            f"CREATE ROLE {RUNTIME_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        # Use a real non-superuser login. SET ROLE from a superuser session
        # would not prove that the application credential lacks escalation.
        cls.admin.execute(
            f"CREATE ROLE {LOGIN_ROLE} LOGIN NOINHERIT NOSUPERUSER "
            f"NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '{LOGIN_PASSWORD}'"
        )
        cls.admin.execute(f"GRANT {RUNTIME_ROLE} TO {LOGIN_ROLE}")
        cls.admin.execute(f"CREATE SCHEMA {SCHEMA} AUTHORIZATION {VERIFIER_ROLE}")
        cls.admin.execute(
            f"CREATE TABLE {SCHEMA}.signing_keys "
            "(key_id text PRIMARY KEY, secret bytea NOT NULL, enabled boolean NOT NULL)"
        )
        cls.admin.execute(
            f"ALTER TABLE {SCHEMA}.signing_keys OWNER TO {VERIFIER_ROLE}"
        )
        cls.admin.execute(
            f"INSERT INTO {SCHEMA}.signing_keys VALUES ('active', %s, true)",
            (ISSUER_KEY,),
        )
        cls.admin.execute(
            f"CREATE TABLE {SCHEMA}.tenant_rows "
            "(tenant_id text NOT NULL, row_id text NOT NULL, value text NOT NULL, "
            "PRIMARY KEY (tenant_id, row_id))"
        )
        cls.admin.execute(
            f"INSERT INTO {SCHEMA}.tenant_rows VALUES "
            "('tenant-a','a1','A secret 1'),"
            "('tenant-a','a2','A secret 2'),"
            "('tenant-b','b1','B secret')"
        )
        cls.admin.execute(
            f"ALTER TABLE {SCHEMA}.tenant_rows ENABLE ROW LEVEL SECURITY"
        )
        cls.admin.execute(
            f"ALTER TABLE {SCHEMA}.tenant_rows FORCE ROW LEVEL SECURITY"
        )

        verifier_sql = f"""
        CREATE FUNCTION {SCHEMA}.verify_tenant_assertion(
            token text,
            expected_tenant text,
            expected_audience text,
            expected_action text,
            expected_resource text
        ) RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, {SCHEMA}
        AS $verifier$
        DECLARE
            payload_part text;
            signature_part text;
            payload_bytes bytea;
            signature_bytes bytea;
            expected_signature bytea;
            key_material bytea;
            claims jsonb;
            issued_at bigint;
            expires_at bigint;
            current_epoch bigint;
            diff integer := 0;
            i integer;
        BEGIN
            IF token IS NULL OR length(token) > 8192
               OR token !~ '^[A-Za-z0-9_-]+[.][A-Za-z0-9_-]+$' THEN
                RETURN false;
            END IF;

            payload_part := split_part(token, '.', 1);
            signature_part := split_part(token, '.', 2);
            payload_bytes := decode(
                rpad(translate(payload_part, '-_', '+/'),
                     ((length(payload_part) + 3) / 4) * 4, '='),
                'base64'
            );
            signature_bytes := decode(
                rpad(translate(signature_part, '-_', '+/'),
                     ((length(signature_part) + 3) / 4) * 4, '='),
                'base64'
            );
            IF octet_length(signature_bytes) <> 32 THEN
                RETURN false;
            END IF;

            SELECT secret INTO key_material
              FROM {SCHEMA}.signing_keys
             WHERE key_id = 'active' AND enabled = true;
            IF NOT FOUND OR key_material IS NULL THEN
                RETURN false;
            END IF;

            expected_signature := public.hmac(
                convert_to(payload_part, 'UTF8'), key_material, 'sha256'
            );
            -- Fixed 32-byte loop avoids an early-exit bytea comparison.
            FOR i IN 0..31 LOOP
                diff := diff | (get_byte(signature_bytes, i) # get_byte(expected_signature, i));
            END LOOP;
            IF diff <> 0 THEN
                RETURN false;
            END IF;

            claims := convert_from(payload_bytes, 'UTF8')::jsonb;
            IF jsonb_typeof(claims) IS DISTINCT FROM 'object'
               OR NOT (claims ?& ARRAY[
                   'v','tenant_id','sub','aud','action','resource_id','iat','exp','nonce'
               ])
               OR claims - ARRAY[
                   'v','tenant_id','sub','aud','action','resource_id','iat','exp','nonce'
               ] <> '{{}}'::jsonb THEN
                RETURN false;
            END IF;

            IF jsonb_typeof(claims->'v') IS DISTINCT FROM 'number'
               OR claims->>'v' <> '1'
               OR jsonb_typeof(claims->'iat') IS DISTINCT FROM 'number'
               OR jsonb_typeof(claims->'exp') IS DISTINCT FROM 'number' THEN
                RETURN false;
            END IF;

            IF jsonb_typeof(claims->'tenant_id') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'sub') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'aud') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'action') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'resource_id') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'nonce') IS DISTINCT FROM 'string'
               OR length(claims->>'tenant_id') NOT BETWEEN 1 AND 256
               OR length(claims->>'sub') NOT BETWEEN 1 AND 256
               OR length(claims->>'aud') NOT BETWEEN 1 AND 256
               OR length(claims->>'action') NOT BETWEEN 1 AND 256
               OR length(claims->>'resource_id') NOT BETWEEN 1 AND 256
               OR length(claims->>'nonce') NOT BETWEEN 1 AND 256 THEN
                RETURN false;
            END IF;

            IF (claims->>'iat')::numeric <> trunc((claims->>'iat')::numeric)
               OR (claims->>'exp')::numeric <> trunc((claims->>'exp')::numeric) THEN
                RETURN false;
            END IF;
            issued_at := (claims->>'iat')::bigint;
            expires_at := (claims->>'exp')::bigint;
            current_epoch := floor(extract(epoch FROM statement_timestamp()))::bigint;

            IF issued_at > current_epoch
               OR expires_at <= current_epoch
               OR expires_at <= issued_at
               OR expires_at - issued_at > {MAX_LIFETIME_SECONDS} THEN
                RETURN false;
            END IF;

            IF claims->>'tenant_id' IS DISTINCT FROM expected_tenant
               OR claims->>'aud' IS DISTINCT FROM expected_audience
               OR claims->>'action' IS DISTINCT FROM expected_action
               OR claims->>'resource_id' IS DISTINCT FROM expected_resource THEN
                RETURN false;
            END IF;
            RETURN true;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN false;
        END;
        $verifier$
        """
        cls.admin.execute(verifier_sql)
        cls.admin.execute(
            f"ALTER FUNCTION {SCHEMA}.verify_tenant_assertion(text,text,text,text,text) "
            f"OWNER TO {VERIFIER_ROLE}"
        )
        cls.admin.execute(
            f"REVOKE ALL ON FUNCTION {SCHEMA}.verify_tenant_assertion(text,text,text,text,text) FROM PUBLIC"
        )
        cls.admin.execute(
            f"GRANT USAGE ON SCHEMA {SCHEMA} TO {RUNTIME_ROLE}"
        )
        cls.admin.execute(
            f"GRANT EXECUTE ON FUNCTION {SCHEMA}.verify_tenant_assertion(text,text,text,text,text) "
            f"TO {RUNTIME_ROLE}"
        )
        cls.admin.execute(
            f"GRANT SELECT, UPDATE ON {SCHEMA}.tenant_rows TO {RUNTIME_ROLE}"
        )
        cls.admin.execute(
            f"CREATE POLICY tenant_read ON {SCHEMA}.tenant_rows FOR SELECT "
            f"USING ({SCHEMA}.verify_tenant_assertion("
            "current_setting('app.tenant_assertion', true), tenant_id, "
            "'stemlab-api', 'read', row_id) OR "
            f"{SCHEMA}.verify_tenant_assertion("
            "current_setting('app.tenant_assertion', true), tenant_id, "
            "'stemlab-api', 'update', row_id))"
        )
        cls.admin.execute(
            f"CREATE POLICY tenant_update ON {SCHEMA}.tenant_rows FOR UPDATE "
            f"USING ({SCHEMA}.verify_tenant_assertion("
            "current_setting('app.tenant_assertion', true), tenant_id, "
            "'stemlab-api', 'update', row_id)) "
            f"WITH CHECK ({SCHEMA}.verify_tenant_assertion("
            "current_setting('app.tenant_assertion', true), tenant_id, "
            "'stemlab-api', 'update', row_id))"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cls.admin.execute(f"DROP ROLE IF EXISTS {LOGIN_ROLE}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {RUNTIME_ROLE}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {VERIFIER_ROLE}")
        cls.admin.close()

    def connect_as_runtime(self):
        runtime_dsn = make_conninfo(
            DSN, user=LOGIN_ROLE, password=LOGIN_PASSWORD
        )
        conn = psycopg.connect(runtime_dsn, autocommit=True)
        conn.execute(f"SET ROLE {RUNTIME_ROLE}")
        return conn

    def rows_for(self, token: str | None, *, row_id: str | None = None):
        with self.connect_as_runtime() as conn:
            with conn.transaction():
                conn.execute(
                    "SELECT set_config('app.tenant_assertion', %s, true)",
                    (token or "",),
                )
                if row_id is None:
                    return conn.execute(
                        f"SELECT row_id, value FROM {SCHEMA}.tenant_rows ORDER BY row_id"
                    ).fetchall()
                return conn.execute(
                    f"SELECT row_id, value FROM {SCHEMA}.tenant_rows WHERE row_id=%s",
                    (row_id,),
                ).fetchall()

    def test_valid_assertion_reads_only_its_exact_tenant_resource(self):
        token = issue_assertion(tenant_id="tenant-a", resource_id="a1")
        self.assertEqual(self.rows_for(token), [("a1", "A secret 1")])

    def test_missing_assertion_fails_closed(self):
        self.assertEqual(self.rows_for(None), [])

    def test_forged_signature_fails_closed(self):
        token = tamper_signature(issue_assertion())
        self.assertEqual(self.rows_for(token), [])

    def test_tenant_claim_mutation_without_resigning_fails_closed(self):
        token = tamper_payload_without_resigning(
            issue_assertion(tenant_id="tenant-a"), tenant_id="tenant-b"
        )
        self.assertEqual(self.rows_for(token), [])

    def test_valid_tenant_a_assertion_cannot_read_tenant_b_even_if_plain_guc_is_spoofed(self):
        token = issue_assertion(tenant_id="tenant-a", resource_id="a1")
        with self.connect_as_runtime() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id','tenant-b',true)")
                conn.execute("SELECT set_config('app.tenant_assertion',%s,true)", (token,))
                self.assertEqual(
                    conn.execute(f"SELECT row_id FROM {SCHEMA}.tenant_rows ORDER BY row_id").fetchall(),
                    [("a1",)],
                )

    def test_assertion_cannot_be_replayed_for_another_resource(self):
        token = issue_assertion(tenant_id="tenant-a", resource_id="a1")
        self.assertEqual(self.rows_for(token, row_id="a2"), [])

    def test_audience_and_action_mismatch_fail_closed(self):
        wrong_audience = issue_assertion(audience="other-service")
        wrong_action = issue_assertion(action="delete")
        self.assertEqual(self.rows_for(wrong_audience), [])
        self.assertEqual(self.rows_for(wrong_action), [])

    def test_expired_and_future_assertions_fail_closed(self):
        import time

        now = int(time.time())
        expired = issue_assertion(issued_at=now - 120, expires_at=now - 1)
        future = issue_assertion(issued_at=now + 60, expires_at=now + 90)
        self.assertEqual(self.rows_for(expired), [])
        self.assertEqual(self.rows_for(future), [])

    def test_update_requires_an_update_scoped_assertion(self):
        read_token = issue_assertion(action="read")
        update_token = issue_assertion(action="update")
        with self.connect_as_runtime() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_assertion',%s,true)", (read_token,))
                result = conn.execute(
                    f"UPDATE {SCHEMA}.tenant_rows SET value='changed' "
                    "WHERE tenant_id='tenant-a' AND row_id='a1'"
                )
                self.assertEqual(result.rowcount, 0)
            try:
                with conn.transaction():
                    conn.execute("SELECT set_config('app.tenant_assertion',%s,true)", (update_token,))
                    result = conn.execute(
                        f"UPDATE {SCHEMA}.tenant_rows SET value='changed' "
                        "WHERE tenant_id='tenant-a' AND row_id='a1'"
                    )
                    self.assertEqual(result.rowcount, 1)
                    # Keep tests order-independent: this assertion checks the
                    # UPDATE policy, not durable fixture mutation.
                    raise RuntimeError("rollback verifier update fixture")
            except RuntimeError as exc:
                self.assertEqual(str(exc), "rollback verifier update fixture")

    def test_runtime_cannot_read_signing_key_or_change_it(self):
        with self.connect_as_runtime() as conn:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT secret FROM {SCHEMA}.signing_keys")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    f"UPDATE {SCHEMA}.signing_keys SET enabled=false WHERE key_id='active'"
                )

    def test_runtime_cannot_replace_verifier_function(self):
        with self.connect_as_runtime() as conn:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    f"CREATE OR REPLACE FUNCTION {SCHEMA}.verify_tenant_assertion("
                    "text,text,text,text,text) RETURNS boolean LANGUAGE sql "
                    "AS 'SELECT true'"
                )

    def test_runtime_cannot_assume_verifier_owner_or_bypass_rls(self):
        with self.connect_as_runtime() as conn:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SET ROLE {VERIFIER_ROLE}")
            row = conn.execute(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            self.assertEqual(row, (False, False))
            owns_table = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=%s AND c.relname='tenant_rows' "
                "AND pg_get_userbyid(c.relowner)=current_user)",
                (SCHEMA,),
            ).fetchone()[0]
            self.assertFalse(owns_table)


if __name__ == "__main__":
    unittest.main(verbosity=2)
