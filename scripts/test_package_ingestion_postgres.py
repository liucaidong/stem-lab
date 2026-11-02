#!/usr/bin/env python3
"""PostgreSQL transaction/RLS harness for Package ingestion lifecycle receipts."""
from __future__ import annotations
import json, os, threading, unittest, uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import psycopg
from psycopg import errors

DSN = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stemlab_test")
SCHEMA = "stemlab_ingest_" + uuid.uuid4().hex[:10]
ROLE = "stemlab_ingestion_app"

def admin():
    return psycopg.connect(DSN, autocommit=True)

@contextmanager
def app_conn(tenant):
    conn = psycopg.connect(DSN)
    try:
        with conn.transaction():
            conn.execute(f"SET LOCAL ROLE {ROLE}")
            conn.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
            yield conn
    finally:
        conn.close()

class RevisionConflict(Exception):
    pass

class IdempotencyConflict(Exception):
    pass

ALLOWED = {
    "created": {"receiving", "rejected", "expired"},
    "receiving": {"received", "rejected", "expired"},
    "received": {"quarantined", "rejected", "expired"},
    "quarantined": {"validating", "rejected", "expired"},
    "validating": {"validated", "rejected", "quarantined"},
    "validated": {"revoked"},
    "rejected": set(), "revoked": set(), "expired": set()
}

def apply_transition(conn, tenant, session_id, expected_revision, to_state,
                     command_id, idempotency_key, request_digest, fail_outbox=False):
    with conn.transaction():
        conn.execute(f"SET LOCAL ROLE {ROLE}")
        conn.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
        inserted = conn.execute(
            """INSERT INTO receipts
               (tenant_id,session_id,operation,idempotency_key,request_digest,response_json)
               VALUES (%s,%s,'transition',%s,%s,NULL)
               ON CONFLICT DO NOTHING RETURNING idempotency_key""",
            (tenant, session_id, idempotency_key, request_digest)
        ).fetchone()
        if inserted is None:
            prior = conn.execute(
                """SELECT request_digest,response_json FROM receipts
                   WHERE tenant_id=%s AND session_id=%s AND operation='transition' AND idempotency_key=%s""",
                (tenant, session_id, idempotency_key)
            ).fetchone()
            if prior is None:
                raise RuntimeError("idempotency conflict row disappeared")
            if prior[0] != request_digest:
                raise IdempotencyConflict()
            return {"outcome": "REPLAY_EXISTING_RECEIPT", "receipt": prior[1]}

        row = conn.execute(
            """SELECT status,revision FROM sessions
               WHERE tenant_id=%s AND session_id=%s FOR UPDATE""",
            (tenant, session_id)
        ).fetchone()
        if row is None:
            raise KeyError("session not found")
        current_state, current_revision = row
        if current_revision != expected_revision:
            raise RevisionConflict()
        if to_state not in ALLOWED[current_state]:
            raise ValueError("illegal transition")
        next_revision = current_revision + 1
        sequence = next_revision - 1
        conn.execute(
            """UPDATE sessions SET status=%s,revision=%s,updated_at=now()
               WHERE tenant_id=%s AND session_id=%s AND revision=%s""",
            (to_state, next_revision, tenant, session_id, expected_revision)
        )
        conn.execute(
            """INSERT INTO transitions
               (tenant_id,session_id,sequence,from_state,to_state,command_id,idempotency_key,
                request_digest,actor_id,expected_revision,resulting_revision)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'test-actor',%s,%s)""",
            (tenant, session_id, sequence, current_state, to_state, command_id,
             idempotency_key, request_digest, expected_revision, next_revision)
        )
        if fail_outbox:
            # Inject a deterministic failure after session/transition writes.
            raise RuntimeError("injected outbox failure")
        conn.execute(
            """INSERT INTO outbox
               (tenant_id,event_id,session_id,sequence,event_type,payload)
               VALUES (%s,%s,%s,%s,'package.ingestion.transitioned',%s::jsonb)""",
            (tenant, command_id, session_id, sequence,
             json.dumps({"from": current_state, "to": to_state, "revision": next_revision}))
        )
        receipt = {"session_id": session_id, "status": to_state, "revision": next_revision}
        conn.execute(
            """UPDATE receipts SET response_json=%s::jsonb
               WHERE tenant_id=%s AND session_id=%s AND operation='transition' AND idempotency_key=%s""",
            (json.dumps(receipt), tenant, session_id, idempotency_key)
        )
        return {"outcome": "APPLIED", "receipt": receipt}

class PackageIngestionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = admin()
        cls.a.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{ROLE}') "
            f"THEN CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; END IF; END $$"
        )
        cls.a.execute(f"CREATE SCHEMA {SCHEMA}")
        cls.a.execute(f"""
            CREATE TABLE {SCHEMA}.sessions(
                tenant_id text NOT NULL, session_id text NOT NULL,
                package_id text NOT NULL, package_version text NOT NULL,
                status text NOT NULL CHECK(status IN
                  ('created','receiving','received','quarantined','validating','validated','rejected','revoked','expired')),
                revision integer NOT NULL CHECK(revision > 0),
                updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY(tenant_id,session_id)
            );
            CREATE TABLE {SCHEMA}.transitions(
                tenant_id text NOT NULL, session_id text NOT NULL, sequence integer NOT NULL,
                from_state text NOT NULL, to_state text NOT NULL, command_id text NOT NULL,
                idempotency_key text NOT NULL, request_digest text NOT NULL,
                actor_id text NOT NULL, expected_revision integer NOT NULL,
                resulting_revision integer NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY(tenant_id,session_id,sequence),
                UNIQUE(tenant_id,session_id,command_id),
                UNIQUE(tenant_id,session_id,idempotency_key),
                FOREIGN KEY(tenant_id,session_id) REFERENCES {SCHEMA}.sessions(tenant_id,session_id)
            );
            CREATE TABLE {SCHEMA}.receipts(
                tenant_id text NOT NULL, session_id text NOT NULL, operation text NOT NULL,
                idempotency_key text NOT NULL, request_digest text NOT NULL, response_json jsonb,
                PRIMARY KEY(tenant_id,session_id,operation,idempotency_key),
                FOREIGN KEY(tenant_id,session_id) REFERENCES {SCHEMA}.sessions(tenant_id,session_id)
            );
            CREATE TABLE {SCHEMA}.outbox(
                tenant_id text NOT NULL, event_id text NOT NULL, session_id text NOT NULL,
                sequence integer NOT NULL, event_type text NOT NULL, payload jsonb NOT NULL,
                published_at timestamptz,
                PRIMARY KEY(tenant_id,event_id), UNIQUE(tenant_id,session_id,sequence),
                FOREIGN KEY(tenant_id,session_id) REFERENCES {SCHEMA}.sessions(tenant_id,session_id)
            );
            CREATE FUNCTION {SCHEMA}.deny_transition_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'transition ledger is append-only'
              USING ERRCODE='55000'; END $$;
            CREATE TRIGGER transitions_append_only BEFORE UPDATE OR DELETE ON {SCHEMA}.transitions
              FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.deny_transition_mutation();
        """)
        for table in ("sessions", "transitions", "receipts", "outbox"):
            cls.a.execute(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")
            cls.a.execute(f"ALTER TABLE {SCHEMA}.{table} FORCE ROW LEVEL SECURITY")
            cls.a.execute(
                f"CREATE POLICY tenant_isolation ON {SCHEMA}.{table} "
                "USING (tenant_id=current_setting('app.tenant_id',true)) "
                "WITH CHECK (tenant_id=current_setting('app.tenant_id',true))"
            )
            if table == "transitions":
                cls.a.execute(f"GRANT SELECT,INSERT ON {SCHEMA}.{table} TO {ROLE}")
            else:
                cls.a.execute(f"GRANT SELECT,INSERT,UPDATE ON {SCHEMA}.{table} TO {ROLE}")
        cls.a.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {ROLE}")

    @classmethod
    def tearDownClass(cls):
        cls.a.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cls.a.execute(f"DROP ROLE IF EXISTS {ROLE}")
        cls.a.close()

    def setUp(self):
        self.a.execute(f"TRUNCATE {SCHEMA}.outbox,{SCHEMA}.receipts,{SCHEMA}.transitions,{SCHEMA}.sessions CASCADE")
        self.a.execute(f"INSERT INTO {SCHEMA}.sessions(tenant_id,session_id,package_id,package_version,status,revision) VALUES ('A','s1','pkg','1.0.0','created',1),('B','s1','pkg','1.0.0','created',1)")

    def run_transition(self, tenant="A", expected=1, key="key-1", digest="sha256:"+"1"*64, command="cmd-1", fail=False):
        with app_conn(tenant) as conn:
            return apply_transition(conn, tenant, "s1", expected, "receiving", command, key, digest, fail)

    def test_atomic_transition_receipt_and_outbox(self):
        result = self.run_transition()
        self.assertEqual(result["outcome"], "APPLIED")
        self.assertEqual(self.a.execute(f"SELECT status,revision FROM {SCHEMA}.sessions WHERE tenant_id='A'").fetchone(), ("receiving",2))
        self.assertEqual(self.a.execute(f"SELECT count(*) FROM {SCHEMA}.transitions").fetchone()[0],1)
        self.assertEqual(self.a.execute(f"SELECT count(*) FROM {SCHEMA}.receipts").fetchone()[0],1)
        self.assertEqual(self.a.execute(f"SELECT count(*) FROM {SCHEMA}.outbox").fetchone()[0],1)

    def test_same_idempotency_key_same_digest_replays_receipt(self):
        first = self.run_transition()
        second = self.run_transition()
        self.assertEqual(first["receipt"], second["receipt"])
        self.assertEqual(second["outcome"], "REPLAY_EXISTING_RECEIPT")
        self.assertEqual(self.a.execute(f"SELECT count(*) FROM {SCHEMA}.transitions").fetchone()[0],1)

    def test_same_idempotency_key_different_digest_conflicts(self):
        self.run_transition()
        with self.assertRaises(IdempotencyConflict):
            self.run_transition(digest="sha256:"+"2"*64, command="cmd-2")

    def test_stale_revision_rolls_back_receipt(self):
        with self.assertRaises(RevisionConflict):
            self.run_transition(expected=99)
        self.assertEqual(self.a.execute(f"SELECT count(*) FROM {SCHEMA}.receipts").fetchone()[0],0)
        self.assertEqual(self.a.execute(f"SELECT status,revision FROM {SCHEMA}.sessions WHERE tenant_id='A'").fetchone(), ("created",1))

    def test_outbox_failure_rolls_back_state_transition_and_receipt(self):
        with self.assertRaises(RuntimeError):
            self.run_transition(fail=True)
        self.assertEqual(self.a.execute(f"SELECT status,revision FROM {SCHEMA}.sessions WHERE tenant_id='A'").fetchone(), ("created",1))
        self.assertEqual(self.a.execute(f"SELECT count(*) FROM {SCHEMA}.transitions").fetchone()[0],0)
        self.assertEqual(self.a.execute(f"SELECT count(*) FROM {SCHEMA}.receipts").fetchone()[0],0)
        self.assertEqual(self.a.execute(f"SELECT count(*) FROM {SCHEMA}.outbox").fetchone()[0],0)

    def test_rls_tenant_isolation(self):
        with app_conn("A") as conn:
            rows = conn.execute("SELECT tenant_id FROM sessions").fetchall()
            self.assertEqual(rows,[("A",)])
            self.assertEqual(conn.execute("SELECT count(*) FROM transitions").fetchone()[0],0)

    def test_transition_ledger_is_append_only(self):
        self.run_transition()
        with self.assertRaises(errors.ObjectNotInPrerequisiteState):
            with app_conn("A") as conn:
                conn.execute("UPDATE transitions SET to_state='received' WHERE session_id='s1'")

    def test_parallel_stale_revision_race_has_one_winner(self):
        barrier = threading.Barrier(2)
        def contender(index):
            barrier.wait()
            try:
                return self.run_transition(key=f"race-{index}",command=f"race-cmd-{index}")["outcome"]
            except RevisionConflict:
                return "REVISION_CONFLICT"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(contender,[1,2]))
        self.assertEqual(results.count("APPLIED"),1)
        self.assertEqual(results.count("REVISION_CONFLICT"),1)
        self.assertEqual(self.a.execute(f"SELECT revision FROM {SCHEMA}.sessions WHERE tenant_id='A'").fetchone()[0],2)
        self.assertEqual(self.a.execute(f"SELECT count(*) FROM outbox WHERE tenant_id='A'").fetchone()[0],1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
