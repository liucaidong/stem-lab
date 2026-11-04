#!/usr/bin/env python3
"""PostgreSQL v2alpha2 atomic Business Handler, nonce, RLS and reconciliation conformance."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
import pathlib
import sys
import time
import uuid

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DSN = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stemlab_test")
SCHEMA = "worker_uow_" + uuid.uuid4().hex[:10]
OWNER_ROLE = "uow_owner_" + uuid.uuid4().hex[:8]
RUNTIME_ROLE = "uow_runtime_" + uuid.uuid4().hex[:8]

from runtime.postgres_worker_store import PostgresWorkerStore


def sign_claim(conn, private_key, envelope):
    digest = conn.execute(
        f"SELECT {SCHEMA}.request_digest_v2alpha2(%s::jsonb)",
        (json.dumps(envelope, ensure_ascii=False),),
    ).fetchone()[0]
    claim = {key: value for key, value in envelope.items() if key != "operation_arguments"}
    now = int(time.time())
    claim.update({
        "v": 2,
        "iss": "test-issuer",
        "kid": "test-key",
        "sub": "worker-a",
        "aud": "stemlab-worker-store",
        "owner": "worker-a",
        "epoch": 7,
        "request_digest": digest,
        "iat": now,
        "exp": now + 60,
        "nonce": uuid.uuid4().hex,
    })
    raw = json.dumps(claim, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    signature = conn.execute(
        "SELECT pgsodium.crypto_sign_detached(%s,%s)", (raw, private_key)
    ).fetchone()[0]
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return payload_b64, signature_b64, claim, digest


def complete_envelope(job_id, session_id, operation_id, idempotency_key,
                      result_ref="artifact:abc", expected_revision=7):
    return {
        "contract_version": "2alpha2",
        "action": "worker.job.complete",
        "tenant_id": "tenant-a",
        "job_id": job_id,
        "session_id": session_id,
        "resource_type": "job",
        "resource_id": job_id,
        "operation_id": operation_id,
        "idempotency_key": idempotency_key,
        "operation_arguments": {
            "expected_session_revision": expected_revision,
            "result_ref": result_ref,
        },
    }


def reconcile_envelope(job_id, session_id, operation_id, idempotency_key):
    return {
        "contract_version": "2alpha2",
        "action": "worker.receipt.reconcile",
        "tenant_id": "tenant-a",
        "job_id": job_id,
        "session_id": session_id,
        "resource_type": "receipt",
        "resource_id": operation_id,
        "operation_id": operation_id,
        "idempotency_key": idempotency_key,
        "operation_arguments": {},
    }


def insert_session_and_job(conn, job_id, session_id):
    conn.execute(
        f"""INSERT INTO {SCHEMA}.sessions
             (tenant_id,session_id,package_id,package_version,status,revision)
             VALUES ('tenant-a',%s,'pkg','1.0.0','quarantined',7)""",
        (session_id,),
    )
    conn.execute(
        f"""INSERT INTO {SCHEMA}.ingestion_jobs
             (tenant_id,job_id,session_id,package_id,package_version,job_type,status,
              attempt_count,maximum_attempts,lease_owner,lease_expires_at,lease_epoch)
             VALUES ('tenant-a',%s,%s,'pkg','1.0.0','package.validate','running',
                     1,5,'worker-a',clock_timestamp()+interval '5 minutes',7)""",
        (job_id, session_id),
    )


def snapshot(conn, session_id, job_id):
    session = conn.execute(
        f"SELECT status,revision FROM {SCHEMA}.sessions WHERE tenant_id='tenant-a' AND session_id=%s",
        (session_id,),
    ).fetchone()
    job = conn.execute(
        f"SELECT status,lease_owner,lease_epoch FROM {SCHEMA}.ingestion_jobs WHERE tenant_id='tenant-a' AND job_id=%s",
        (job_id,),
    ).fetchone()
    counts = conn.execute(
        f"""SELECT
          (SELECT count(*) FROM {SCHEMA}.transitions WHERE tenant_id='tenant-a' AND session_id=%s),
          (SELECT count(*) FROM {SCHEMA}.outbox WHERE tenant_id='tenant-a' AND session_id=%s),
          (SELECT count(*) FROM {SCHEMA}.request_receipts_v2alpha2 WHERE tenant_id='tenant-a'),
          (SELECT count(*) FROM {SCHEMA}.request_nonce_ledger_v2alpha2 WHERE tenant_id='tenant-a')""",
        (session_id, session_id),
    ).fetchone()
    return session, job, counts



class LostCommitAckConnection:
    """Connection proxy that commits successfully, then simulates a lost COMMIT acknowledgement."""
    def __init__(self, connection):
        self._connection = connection

    def execute(self, *args, **kwargs):
        return self._connection.execute(*args, **kwargs)

    def close(self):
        return self._connection.close()

    def transaction(self):
        return LostCommitAckContext(self._connection.transaction())


class LostCommitAckContext:
    def __init__(self, transaction):
        self._transaction = transaction

    def __enter__(self):
        return self._transaction.__enter__()

    def __exit__(self, exc_type, exc, tb):
        result = self._transaction.__exit__(exc_type, exc, tb)
        if exc_type is None:
            raise psycopg.OperationalError("simulated lost COMMIT acknowledgement after server commit")
        return result


def main() -> None:
    conn = psycopg.connect(DSN, autocommit=True)
    try:
        encoding = conn.execute("SHOW server_encoding").fetchone()[0]
        assert encoding.upper() == "UTF8", f"PostgreSQL encoding must be UTF8, got {encoding}"
        conn.execute("CREATE EXTENSION IF NOT EXISTS pgsodium")
        conn.execute("LOAD 'pgsodium'")
        public_key, private_key = conn.execute(
            "SELECT public,secret FROM pgsodium.crypto_sign_new_keypair()"
        ).fetchone()
        conn.execute(f"CREATE SCHEMA {SCHEMA}")
        conn.execute(
            f"CREATE ROLE {OWNER_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        conn.execute(
            f"CREATE ROLE {RUNTIME_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
        )
        conn.execute(
            f"""CREATE TABLE {SCHEMA}.issuer_keys (
              kid text PRIMARY KEY, issuer text NOT NULL, public_key bytea NOT NULL,
              not_before timestamptz NOT NULL, not_after timestamptz, revoked_at timestamptz
            )"""
        )
        conn.execute(
            f"INSERT INTO {SCHEMA}.issuer_keys(kid,issuer,public_key,not_before) "
            "VALUES ('test-key','test-issuer',%s,clock_timestamp()-interval '1 day')",
            (public_key,),
        )
        digest_sql = (ROOT / "sql/request-digest-v2alpha2.sql").read_text().replace("__SCHEMA__", SCHEMA)
        conn.execute(digest_sql, prepare=False)

        conn.execute(f"""
          CREATE TABLE {SCHEMA}.sessions(
            tenant_id text NOT NULL,session_id text NOT NULL,package_id text NOT NULL,
            package_version text NOT NULL,status text NOT NULL,revision integer NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY(tenant_id,session_id));
          CREATE TABLE {SCHEMA}.transitions(
            tenant_id text NOT NULL,session_id text NOT NULL,sequence integer NOT NULL,
            from_state text NOT NULL,to_state text NOT NULL,command_id text NOT NULL,
            idempotency_key text NOT NULL,request_digest text NOT NULL,actor_id text NOT NULL,
            expected_revision integer NOT NULL,resulting_revision integer NOT NULL,
            PRIMARY KEY(tenant_id,session_id,sequence),
            UNIQUE(tenant_id,session_id,command_id),
            FOREIGN KEY(tenant_id,session_id) REFERENCES {SCHEMA}.sessions(tenant_id,session_id));
          CREATE TABLE {SCHEMA}.outbox(
            tenant_id text NOT NULL,event_id text NOT NULL,session_id text NOT NULL,
            sequence integer NOT NULL,event_type text NOT NULL,payload jsonb NOT NULL,
            PRIMARY KEY(tenant_id,event_id),UNIQUE(tenant_id,session_id,sequence),
            FOREIGN KEY(tenant_id,session_id) REFERENCES {SCHEMA}.sessions(tenant_id,session_id));
        """, prepare=False)
        # pgsodium 3.1.11 installs a DDL event trigger that reads this custom GUC.
        # The test schema uses ordinary bytea/public-key tables, not pgsodium masks.
        conn.execute("SELECT set_config('pgsodium.enable_event_trigger','off',false)")
        worker_sql = (ROOT / "sql/package-ingestion-worker/R03.51-ingestion-worker.sql").read_text().replace("stemlab_ingest", SCHEMA)
        conn.execute(worker_sql, prepare=False)
        receipt_sql = (ROOT / "sql/request-receipt-v2alpha2.sql").read_text().replace("__SCHEMA__", SCHEMA)
        conn.execute(receipt_sql, prepare=False)
        nonce_sql = (ROOT / "sql/request-nonce-ledger-v2alpha2.sql").read_text().replace("__SCHEMA__", SCHEMA)
        conn.execute(nonce_sql, prepare=False)
        handler_sql = (ROOT / "sql/worker-business-handler-v2alpha2.sql").read_text().replace("__SCHEMA__", SCHEMA)
        conn.execute(handler_sql, prepare=False)

        for table in ("sessions", "transitions", "outbox"):
            conn.execute(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")
            conn.execute(f"ALTER TABLE {SCHEMA}.{table} FORCE ROW LEVEL SECURITY")
            conn.execute(
                f"CREATE POLICY {table}_tenant_isolation ON {SCHEMA}.{table} "
                "USING (tenant_id=current_setting('app.tenant_id',true)) "
                "WITH CHECK (tenant_id=current_setting('app.tenant_id',true))"
            )

        conn.execute(f"GRANT USAGE,CREATE ON SCHEMA {SCHEMA} TO {OWNER_ROLE}")
        conn.execute(
            f"GRANT SELECT,INSERT,UPDATE ON TABLE {SCHEMA}.sessions,{SCHEMA}.ingestion_jobs,"
            f"{SCHEMA}.transitions,{SCHEMA}.outbox,{SCHEMA}.request_receipts_v2alpha2,"
            f"{SCHEMA}.request_nonce_ledger_v2alpha2 TO {OWNER_ROLE}"
        )
        conn.execute(f"GRANT SELECT ON TABLE {SCHEMA}.issuer_keys TO {OWNER_ROLE}")
        conn.execute(f"GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA {SCHEMA} TO {OWNER_ROLE}")
        conn.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {SCHEMA} TO {OWNER_ROLE}")
        conn.execute(
            f"ALTER FUNCTION {SCHEMA}.apply_job_complete_v2alpha2(text,text,jsonb) OWNER TO {OWNER_ROLE}"
        )
        conn.execute(
            f"ALTER FUNCTION {SCHEMA}.reconcile_request_receipt_v2alpha2(text,text,jsonb) OWNER TO {OWNER_ROLE}"
        )
        conn.execute(f"REVOKE CREATE ON SCHEMA {SCHEMA} FROM {OWNER_ROLE}")
        conn.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {RUNTIME_ROLE}")
        conn.execute(f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {SCHEMA} FROM PUBLIC")
        conn.execute(f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {SCHEMA} FROM {RUNTIME_ROLE}")
        conn.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {SCHEMA} FROM {RUNTIME_ROLE}")
        conn.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {SCHEMA} FROM {RUNTIME_ROLE}")
        conn.execute(
            f"GRANT EXECUTE ON FUNCTION {SCHEMA}.apply_job_complete_v2alpha2(text,text,jsonb) TO {RUNTIME_ROLE}"
        )
        conn.execute(
            f"GRANT EXECUTE ON FUNCTION {SCHEMA}.reconcile_request_receipt_v2alpha2(text,text,jsonb) TO {RUNTIME_ROLE}"
        )

        role_state = conn.execute(
            "SELECT rolcanlogin,rolbypassrls FROM pg_roles WHERE rolname=%s",
            (OWNER_ROLE,),
        ).fetchone()
        runtime_role_state = conn.execute(
            "SELECT rolcanlogin,rolbypassrls FROM pg_roles WHERE rolname=%s",
            (RUNTIME_ROLE,),
        ).fetchone()
        assert role_state == (False, False), f"Function owner must be NOLOGIN/NOBYPASSRLS: {role_state}"
        assert runtime_role_state == (False, False), f"Runtime role must be NOLOGIN/NOBYPASSRLS in this test: {runtime_role_state}"
        for table in ("sessions", "ingestion_jobs", "transitions", "outbox",
                      "request_receipts_v2alpha2", "request_nonce_ledger_v2alpha2"):
            rls = conn.execute(
                """SELECT c.relrowsecurity,c.relforcerowsecurity
                     FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname=%s AND c.relname=%s""",
                (SCHEMA, table),
            ).fetchone()
            assert rls == (True, True), f"{table} must ENABLE and FORCE RLS: {rls}"
        for table in ("sessions", "ingestion_jobs", "transitions", "outbox",
                      "request_receipts_v2alpha2", "request_nonce_ledger_v2alpha2"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                allowed = conn.execute(
                    "SELECT has_table_privilege(%s,%s,%s)",
                    (RUNTIME_ROLE, f"{SCHEMA}.{table}", privilege),
                ).fetchone()[0]
                assert not allowed, f"runtime role unexpectedly has {privilege} on {table}"
        assert conn.execute(
            "SELECT has_function_privilege(%s,%s,'EXECUTE')",
            (RUNTIME_ROLE, f"{SCHEMA}.apply_job_complete_v2alpha2(text,text,jsonb)"),
        ).fetchone()[0], "runtime role must execute the handler entry point"
        assert conn.execute(
            "SELECT has_function_privilege(%s,%s,'EXECUTE')",
            (RUNTIME_ROLE, f"{SCHEMA}.reconcile_request_receipt_v2alpha2(text,text,jsonb)"),
        ).fetchone()[0], "runtime role must execute the reconciliation entry point"
        unexpected_exec = conn.execute(
            """SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                 WHERE n.nspname=%s
                   AND p.proname NOT IN ('apply_job_complete_v2alpha2','reconcile_request_receipt_v2alpha2')
                   AND has_function_privilege(%s,p.oid,'EXECUTE')""",
            (SCHEMA, RUNTIME_ROLE),
        ).fetchall()
        assert unexpected_exec == [], f"runtime role has unexpected helper/function EXECUTE: {unexpected_exec}"
        print("PostgreSQL UOW owner/runtime least-privilege and RLS role setup: PASS")

        def runtime_connection():
            c = psycopg.connect(DSN, autocommit=True)
            c.execute(f"SET ROLE {RUNTIME_ROLE}")
            # Deliberately spoof the GUC; the signed claim must overwrite it.
            c.execute("SET app.tenant_id='tenant-b'")
            return c

        store = PostgresWorkerStore(runtime_connection, SCHEMA)
        insert_session_and_job(conn, "job-1", "session-1")
        complete = complete_envelope("job-1", "session-1", "op-01", "idem-01")
        payload, signature, claim, digest = sign_claim(conn, private_key, complete)
        args = complete["operation_arguments"]
        result = store.apply_job_complete(payload, signature, args)
        assert result["status"] == "applied", result
        assert result["outcome"]["session_revision"] == 8, result
        state = snapshot(conn, "session-1", "job-1")
        assert state[0] == ("validated", 8), state
        assert state[1][0] == "succeeded" and state[1][1] is None, state
        assert state[2][0:2] == (1, 1) and state[2][2:] == (1, 1), state
        print("PostgreSQL signed Business Handler atomic Nonce/Receipt/Job/Session/Transition/Outbox UOW: PASS")
        print("PostgreSQL verified-tenant GUC overwrite and RLS-bound writes: PASS")

        direct = runtime_connection()
        try:
            try:
                direct.execute(f"SELECT count(*) FROM {SCHEMA}.sessions")
            except psycopg.Error:
                pass
            else:
                raise AssertionError("runtime role unexpectedly queried tenant table directly")
        finally:
            direct.close()
        print("PostgreSQL runtime role cannot directly query protected tables: PASS")

        try:
            store.apply_job_complete(payload, signature, args)
        except psycopg.Error as exc:
            assert "NONCE_REPLAY" in str(exc), str(exc)
        else:
            raise AssertionError("exact signed nonce replay was accepted")
        print("PostgreSQL exact nonce replay rejected before Receipt arbitration: PASS")

        fresh_payload, fresh_signature, _, _ = sign_claim(conn, private_key, complete)
        duplicate = store.apply_job_complete(fresh_payload, fresh_signature, args)
        assert duplicate["status"] == "duplicate", duplicate
        duplicate_state = snapshot(conn, "session-1", "job-1")
        assert duplicate_state[0:2] == state[0:2]
        assert duplicate_state[2][0:3] == state[2][0:3]
        print("PostgreSQL fresh-nonce exact operation retry returns terminal Receipt without remutation: PASS")

        # Force the first transaction to hold the Job lock while a second fresh-nonce
        # request races on the same Receipt idempotency key.
        insert_session_and_job(conn, "job-concurrent", "session-concurrent")
        concurrent_env = complete_envelope(
            "job-concurrent", "session-concurrent", "op-concurrent", "idem-concurrent"
        )
        concurrent_a = sign_claim(conn, private_key, concurrent_env)
        concurrent_b = sign_claim(conn, private_key, concurrent_env)
        conn.execute(f"""
          CREATE FUNCTION {SCHEMA}.delay_concurrent_job_update() RETURNS trigger
          LANGUAGE plpgsql AS $trigger$
          BEGIN
            IF NEW.job_id='job-concurrent' THEN PERFORM pg_catalog.pg_sleep(0.25); END IF;
            RETURN NEW;
          END;
          $trigger$;
          CREATE TRIGGER delay_concurrent_job_update
            BEFORE UPDATE ON {SCHEMA}.ingestion_jobs
            FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.delay_concurrent_job_update();
        """, prepare=False)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(store.apply_job_complete, concurrent_a[0], concurrent_a[1], concurrent_env["operation_arguments"]),
                    executor.submit(store.apply_job_complete, concurrent_b[0], concurrent_b[1], concurrent_env["operation_arguments"]),
                ]
                concurrent_results = [future.result(timeout=10) for future in futures]
        finally:
            conn.execute(f"DROP TRIGGER IF EXISTS delay_concurrent_job_update ON {SCHEMA}.ingestion_jobs")
            conn.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.delay_concurrent_job_update()")
        concurrent_statuses = sorted(result["status"] for result in concurrent_results)
        assert concurrent_statuses == ["applied", "duplicate"], concurrent_results
        concurrent_state = snapshot(conn, "session-concurrent", "job-concurrent")
        assert concurrent_state[0] == ("validated", 8), concurrent_state
        assert concurrent_state[1][0] == "succeeded", concurrent_state
        assert concurrent_state[2][0:2] == (1, 1), concurrent_state
        assert conn.execute(
            f"SELECT count(*) FROM {SCHEMA}.request_receipts_v2alpha2 WHERE operation_id='op-concurrent'"
        ).fetchone()[0] == 1
        assert conn.execute(
            f"SELECT count(*) FROM {SCHEMA}.request_nonce_ledger_v2alpha2 WHERE operation_id='op-concurrent'"
        ).fetchone()[0] == 2
        print("PostgreSQL concurrent fresh-nonce duplicate requests serialize to one atomic mutation: PASS")

        before_reconcile = snapshot(conn, "session-1", "job-1")
        rec_env = reconcile_envelope("job-1", "session-1", "op-01", "idem-01")
        rec_payload, rec_signature, _, _ = sign_claim(conn, private_key, rec_env)
        rec_result = store.reconcile_request_receipt(rec_payload, rec_signature, {})
        assert rec_result["status"] == "terminal" and rec_result["receipt_status"] == "succeeded", rec_result
        after_reconcile = snapshot(conn, "session-1", "job-1")
        assert after_reconcile[0:2] == before_reconcile[0:2]
        assert after_reconcile[2][0:3] == before_reconcile[2][0:3]
        assert after_reconcile[2][3] == before_reconcile[2][3] + 1
        missing_env = reconcile_envelope("job-1", "session-1", "op-missing", "idem-missing")
        missing_payload, missing_signature, _, _ = sign_claim(conn, private_key, missing_env)
        missing = store.reconcile_request_receipt(missing_payload, missing_signature, {})
        assert missing["status"] == "missing", missing
        print("PostgreSQL read-only Receipt reconciliation terminal/missing paths: PASS")

        conn.execute(
            f"""INSERT INTO {SCHEMA}.request_receipts_v2alpha2
                (tenant_id,action,idempotency_key,operation_id,request_digest,resource_type,resource_id)
                VALUES ('tenant-a','worker.job.complete','idem-pending','op-pending',
                        'sha256:' || repeat('a',64),'job','job-1')"""
        )
        pending_env = reconcile_envelope("job-1", "session-1", "op-pending", "idem-pending")
        pending_payload, pending_signature, _, _ = sign_claim(conn, private_key, pending_env)
        pending = store.reconcile_request_receipt(pending_payload, pending_signature, {})
        assert pending["status"] == "pending", pending
        print("PostgreSQL read-only Receipt reconciliation pending path: PASS")

        insert_session_and_job(conn, "job-fault", "session-fault")
        fault_env = complete_envelope("job-fault", "session-fault", "op-fault", "idem-fault",
                                      "artifact:fault")
        fault_payload, fault_signature, _, _ = sign_claim(conn, private_key, fault_env)
        conn.execute(f"""
          CREATE FUNCTION {SCHEMA}.fail_selected_outbox_insert() RETURNS trigger
          LANGUAGE plpgsql AS $trigger$
          BEGIN
            IF NEW.event_id='op-fault' THEN RAISE EXCEPTION 'OUTBOX_FAILPOINT'; END IF;
            RETURN NEW;
          END;
          $trigger$;
          CREATE TRIGGER fail_selected_outbox_insert
            BEFORE INSERT ON {SCHEMA}.outbox
            FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.fail_selected_outbox_insert();
        """, prepare=False)
        try:
            try:
                store.apply_job_complete(fault_payload, fault_signature, fault_env["operation_arguments"])
            except psycopg.Error as exc:
                assert "OUTBOX_FAILPOINT" in str(exc), str(exc)
            else:
                raise AssertionError("Outbox failpoint did not abort the Unit of Work")
        finally:
            conn.execute(f"DROP TRIGGER IF EXISTS fail_selected_outbox_insert ON {SCHEMA}.outbox")
            conn.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.fail_selected_outbox_insert()")
        fault_state = snapshot(conn, "session-fault", "job-fault")
        assert fault_state[0] == ("quarantined", 7), fault_state
        assert fault_state[1][0] == "running", fault_state
        assert fault_state[2][0:2] == (0, 0), fault_state
        assert conn.execute(
            f"SELECT count(*) FROM {SCHEMA}.request_receipts_v2alpha2 WHERE operation_id='op-fault'"
        ).fetchone()[0] == 0
        assert conn.execute(
            f"SELECT count(*) FROM {SCHEMA}.request_nonce_ledger_v2alpha2 WHERE operation_id='op-fault'"
        ).fetchone()[0] == 0
        print("PostgreSQL fault-injected rollback leaves Nonce/Receipt/Job/Session/Transition/Outbox unchanged: PASS")

        retry_payload, retry_signature, _, _ = sign_claim(conn, private_key, fault_env)
        retried = store.apply_job_complete(retry_payload, retry_signature, fault_env["operation_arguments"])
        assert retried["status"] == "applied", retried
        print("PostgreSQL rollback operation safely retries with a fresh assertion nonce: PASS")

        insert_session_and_job(conn, "job-ambiguous", "session-ambiguous")
        ambiguous_env = complete_envelope("job-ambiguous", "session-ambiguous",
                                          "op-ambiguous", "idem-ambiguous",
                                          "artifact:ambiguous")
        ambiguous_payload, ambiguous_signature, _, _ = sign_claim(conn, private_key, ambiguous_env)
        lost_ack_store = PostgresWorkerStore(
            lambda: LostCommitAckConnection(runtime_connection()), SCHEMA
        )
        try:
            lost_ack_store.apply_job_complete(
                ambiguous_payload, ambiguous_signature, ambiguous_env["operation_arguments"]
            )
        except psycopg.OperationalError as exc:
            assert "simulated lost COMMIT acknowledgement" in str(exc), str(exc)
        else:
            raise AssertionError("COMMIT acknowledgement-loss failpoint did not fire")
        ambiguous_rec_env = reconcile_envelope(
            "job-ambiguous", "session-ambiguous", "op-ambiguous", "idem-ambiguous"
        )
        ambiguous_rec_payload, ambiguous_rec_signature, _, _ = sign_claim(conn, private_key, ambiguous_rec_env)
        ambiguous_rec = store.reconcile_request_receipt(
            ambiguous_rec_payload, ambiguous_rec_signature, {}
        )
        assert ambiguous_rec["status"] == "terminal" and ambiguous_rec["receipt_status"] == "succeeded", ambiguous_rec
        amb_state = snapshot(conn, "session-ambiguous", "job-ambiguous")
        assert amb_state[0] == ("validated", 8) and amb_state[2][0:2] == (1, 1), amb_state
        print("PostgreSQL ambiguous COMMIT acknowledgement loss reconciles to terminal Receipt without duplicate writes: PASS")

        print("RESULT: v2alpha2 first-slice atomic handler, nonce, Receipt, RLS and reconciliation conformance passed")
    finally:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.execute(f"DROP ROLE IF EXISTS {RUNTIME_ROLE}")
        conn.execute(f"DROP ROLE IF EXISTS {OWNER_ROLE}")
        conn.close()


if __name__ == "__main__":
    main()
