#!/usr/bin/env python3
"""Ed25519 PostgreSQL verifier spike using pgsodium.

The signing private keys exist only in this disposable test process. PostgreSQL
stores issuer public keys and verifies signatures inside the RLS call path.
"""
from __future__ import annotations

import base64
import json
import os
import time
import unittest
import uuid

import psycopg
from psycopg.conninfo import make_conninfo

DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/stemlab_test",
)
SUFFIX = uuid.uuid4().hex[:10]
SCHEMA = "tenant_ed25519_" + SUFFIX
RUNTIME_ROLE = "tenant_ed25519_runtime_" + SUFFIX
VERIFIER_ROLE = "tenant_ed25519_owner_" + SUFFIX
LOGIN_ROLE = "tenant_ed25519_login_" + SUFFIX
LOGIN_PASSWORD = uuid.uuid4().hex + uuid.uuid4().hex
ISSUER = "stemlab-test-issuer"
AUDIENCE = "stemlab-api"
MAX_LIFETIME_SECONDS = 120


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def tamper_signature(token: str) -> str:
    payload_part, signature_part = token.split(".")
    signature = bytearray(
        base64.urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4))
    )
    signature[0] ^= 0x01
    return payload_part + "." + b64url(bytes(signature))


def tamper_payload_without_resigning(token: str, **changes: object) -> str:
    payload_part, signature_part = token.split(".")
    raw = base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4))
    payload = json.loads(raw)
    payload.update(changes)
    changed = b64url(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    return changed + "." + signature_part


class PostgreSQLTenantEd25519VerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.admin = psycopg.connect(DSN, autocommit=True)
        cls.admin.execute("CREATE EXTENSION IF NOT EXISTS pgsodium")
        # Load the extension in this migration/admin backend so its custom
        # GUCs are registered before pgsodium's DDL event trigger runs.
        cls.admin.execute("LOAD 'pgsodium'")
        cls.admin.execute("SET pgsodium.enable_event_trigger = 'off'")

        cls.admin.execute(
            f"CREATE ROLE {VERIFIER_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        cls.admin.execute(
            f"CREATE ROLE {RUNTIME_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        cls.admin.execute(
            f"CREATE ROLE {LOGIN_ROLE} LOGIN NOINHERIT NOSUPERUSER "
            f"NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '{LOGIN_PASSWORD}'"
        )
        cls.admin.execute(f"GRANT {RUNTIME_ROLE} TO {LOGIN_ROLE}")
        cls.admin.execute(f"CREATE SCHEMA {SCHEMA} AUTHORIZATION {VERIFIER_ROLE}")

        # The issuer's private keys remain in this test process only. Only
        # public keys are inserted into the database verifier keyring.
        cls.active_public, cls.active_private = cls.admin.execute(
            "SELECT public, secret FROM pgsodium.crypto_sign_new_keypair()"
        ).fetchone()
        cls.revoked_public, cls.revoked_private = cls.admin.execute(
            "SELECT public, secret FROM pgsodium.crypto_sign_new_keypair()"
        ).fetchone()

        cls.admin.execute(
            f"CREATE TABLE {SCHEMA}.issuer_keys ("
            "kid text PRIMARY KEY, issuer text NOT NULL, public_key bytea NOT NULL, "
            "not_before timestamptz NOT NULL, not_after timestamptz, revoked_at timestamptz)"
        )
        # Keep the keyring owned by the migration/admin identity; the
        # verifier owner receives SELECT only, never key lifecycle mutation.
        cls.admin.execute(
            f"GRANT SELECT ON {SCHEMA}.issuer_keys TO {VERIFIER_ROLE}"
        )
        cls.admin.execute(
            f"INSERT INTO {SCHEMA}.issuer_keys "
            "(kid,issuer,public_key,not_before,not_after,revoked_at) "
            "VALUES ('active',%s,%s,clock_timestamp()-interval '1 day',NULL,NULL),"
            "('revoked',%s,%s,clock_timestamp()-interval '1 day',NULL,clock_timestamp())",
            (ISSUER, cls.active_public, ISSUER, cls.revoked_public),
        )

        cls.admin.execute(
            f"CREATE TABLE {SCHEMA}.tenant_rows ("
            "tenant_id text NOT NULL, row_id text NOT NULL, value text NOT NULL, "
            "PRIMARY KEY (tenant_id,row_id))"
        )
        cls.admin.execute(
            f"INSERT INTO {SCHEMA}.tenant_rows VALUES "
            "('tenant-a','a1','A secret 1'),"
            "('tenant-a','a2','A secret 2'),"
            "('tenant-b','b1','B secret')"
        )
        cls.admin.execute(f"ALTER TABLE {SCHEMA}.tenant_rows ENABLE ROW LEVEL SECURITY")
        cls.admin.execute(f"ALTER TABLE {SCHEMA}.tenant_rows FORCE ROW LEVEL SECURITY")

        cls.admin.execute("GRANT USAGE ON SCHEMA pgsodium TO " + VERIFIER_ROLE)
        cls.admin.execute(
            "GRANT EXECUTE ON FUNCTION pgsodium.crypto_sign_verify_detached(bytea,bytea,bytea) "
            f"TO {VERIFIER_ROLE}"
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
            public_key_value bytea;
            claims jsonb;
            issued_at bigint;
            expires_at bigint;
            current_epoch bigint;
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
            IF octet_length(signature_bytes) <> 64 THEN
                RETURN false;
            END IF;

            claims := convert_from(payload_bytes, 'UTF8')::jsonb;
            IF jsonb_typeof(claims) IS DISTINCT FROM 'object'
               OR NOT (claims ?& ARRAY[
                   'v','iss','kid','tenant_id','sub','aud','action','resource_id','iat','exp','nonce'
               ])
               OR claims - ARRAY[
                   'v','iss','kid','tenant_id','sub','aud','action','resource_id','iat','exp','nonce'
               ] <> '{{}}'::jsonb THEN
                RETURN false;
            END IF;

            IF jsonb_typeof(claims->'v') IS DISTINCT FROM 'number'
               OR claims->>'v' <> '1'
               OR jsonb_typeof(claims->'iat') IS DISTINCT FROM 'number'
               OR jsonb_typeof(claims->'exp') IS DISTINCT FROM 'number' THEN
                RETURN false;
            END IF;

            IF jsonb_typeof(claims->'iss') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'kid') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'tenant_id') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'sub') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'aud') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'action') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'resource_id') IS DISTINCT FROM 'string'
               OR jsonb_typeof(claims->'nonce') IS DISTINCT FROM 'string'
               OR length(claims->>'iss') NOT BETWEEN 1 AND 256
               OR length(claims->>'kid') NOT BETWEEN 1 AND 128
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

            SELECT public_key INTO public_key_value
              FROM {SCHEMA}.issuer_keys
             WHERE kid = claims->>'kid'
               AND issuer = claims->>'iss'
               AND revoked_at IS NULL
               AND not_before <= statement_timestamp()
               AND (not_after IS NULL OR not_after > statement_timestamp());
            IF NOT FOUND OR public_key_value IS NULL THEN
                RETURN false;
            END IF;

            IF NOT pgsodium.crypto_sign_verify_detached(
                signature_bytes, convert_to(payload_part, 'UTF8'), public_key_value
            ) THEN
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
        cls.admin.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {RUNTIME_ROLE}")
        cls.admin.execute(
            f"GRANT EXECUTE ON FUNCTION {SCHEMA}.verify_tenant_assertion(text,text,text,text,text) "
            f"TO {RUNTIME_ROLE}"
        )
        cls.admin.execute(
            f"GRANT SELECT ON {SCHEMA}.tenant_rows TO {RUNTIME_ROLE}"
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

    @classmethod
    def tearDownClass(cls) -> None:
        cls.admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cls.admin.execute(f"REVOKE USAGE ON SCHEMA pgsodium FROM {VERIFIER_ROLE}")
        cls.admin.execute(
            "REVOKE EXECUTE ON FUNCTION pgsodium.crypto_sign_verify_detached(bytea,bytea,bytea) "
            f"FROM {VERIFIER_ROLE}"
        )
        cls.admin.execute(f"DROP ROLE IF EXISTS {LOGIN_ROLE}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {RUNTIME_ROLE}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {VERIFIER_ROLE}")
        cls.admin.close()

    @classmethod
    def issue_assertion(
        cls,
        *,
        tenant_id: str = "tenant-a",
        subject: str = "user-1",
        audience: str = AUDIENCE,
        action: str = "read",
        resource_id: str = "a1",
        issued_at: int | None = None,
        expires_at: int | None = None,
        nonce: str = "nonce-1",
        kid: str = "active",
        issuer: str = ISSUER,
        private_key: bytes | None = None,
    ) -> str:
        now = int(time.time())
        payload = {
            "v": 1,
            "iss": issuer,
            "kid": kid,
            "tenant_id": tenant_id,
            "sub": subject,
            "aud": audience,
            "action": action,
            "resource_id": resource_id,
            "iat": now if issued_at is None else issued_at,
            "exp": now + 60 if expires_at is None else expires_at,
            "nonce": nonce,
        }
        encoded = b64url(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        signing_key = private_key or cls.active_private
        signature = cls.admin.execute(
            "SELECT pgsodium.crypto_sign_detached(%s, %s)",
            (encoded.encode("ascii"), signing_key),
        ).fetchone()[0]
        return encoded + "." + b64url(signature)

    def connect_as_runtime(self):
        runtime_dsn = make_conninfo(DSN, user=LOGIN_ROLE, password=LOGIN_PASSWORD)
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

    def test_valid_ed25519_assertion_reads_exact_resource(self):
        token = self.issue_assertion()
        self.assertEqual(self.rows_for(token), [("a1", "A secret 1")])

    def test_missing_assertion_fails_closed(self):
        self.assertEqual(self.rows_for(None), [])

    def test_modified_signature_fails_closed(self):
        self.assertEqual(self.rows_for(tamper_signature(self.issue_assertion())), [])

    def test_tenant_claim_mutation_without_resigning_fails_closed(self):
        token = tamper_payload_without_resigning(
            self.issue_assertion(), tenant_id="tenant-b"
        )
        self.assertEqual(self.rows_for(token), [])

    def test_plain_tenant_guc_cannot_override_signed_tenant(self):
        token = self.issue_assertion(tenant_id="tenant-a")
        with self.connect_as_runtime() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.tenant_id','tenant-b',true)")
                conn.execute(
                    "SELECT set_config('app.tenant_assertion',%s,true)", (token,)
                )
                self.assertEqual(
                    conn.execute(
                        f"SELECT row_id FROM {SCHEMA}.tenant_rows ORDER BY row_id"
                    ).fetchall(),
                    [("a1",)],
                )

    def test_assertion_cannot_be_replayed_for_another_resource(self):
        token = self.issue_assertion(resource_id="a1")
        self.assertEqual(self.rows_for(token, row_id="a2"), [])

    def test_audience_and_action_mismatch_fail_closed(self):
        wrong_audience = self.issue_assertion(audience="other-service")
        wrong_action = self.issue_assertion(action="delete")
        self.assertEqual(self.rows_for(wrong_audience), [])
        self.assertEqual(self.rows_for(wrong_action), [])

    def test_expired_and_future_assertions_fail_closed(self):
        now = int(time.time())
        expired = self.issue_assertion(issued_at=now - 120, expires_at=now - 1)
        future = self.issue_assertion(issued_at=now + 60, expires_at=now + 90)
        self.assertEqual(self.rows_for(expired), [])
        self.assertEqual(self.rows_for(future), [])

    def test_unknown_issuer_key_fails_closed(self):
        token = self.issue_assertion(kid="missing")
        self.assertEqual(self.rows_for(token), [])

    def test_revoked_issuer_key_fails_closed(self):
        token = self.issue_assertion(
            kid="revoked", private_key=self.revoked_private
        )
        self.assertEqual(self.rows_for(token), [])

    def test_runtime_cannot_read_or_change_issuer_keyring(self):
        with self.connect_as_runtime() as conn:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT public_key FROM {SCHEMA}.issuer_keys")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    f"UPDATE {SCHEMA}.issuer_keys SET revoked_at=clock_timestamp()"
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

    def test_temp_table_shadowing_does_not_change_verifier_key_lookup(self):
        token = self.issue_assertion()
        with self.connect_as_runtime() as conn:
            conn.execute("CREATE TEMP TABLE issuer_keys(kid text, public_key bytea)")
            conn.execute(
                "INSERT INTO pg_temp.issuer_keys VALUES ('active', %s)",
                (b"not-a-public-key",),
            )
            with conn.transaction():
                conn.execute(
                    "SELECT set_config('app.tenant_assertion',%s,true)", (token,)
                )
                self.assertEqual(
                    conn.execute(
                        f"SELECT row_id FROM {SCHEMA}.tenant_rows ORDER BY row_id"
                    ).fetchall(),
                    [("a1",)],
                )

    def test_private_signing_key_is_not_persisted_in_keyring(self):
        columns = self.admin.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name='issuer_keys' ORDER BY ordinal_position",
            (SCHEMA,),
        ).fetchall()
        self.assertEqual(
            [row[0] for row in columns],
            ["kid", "issuer", "public_key", "not_before", "not_after", "revoked_at"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
