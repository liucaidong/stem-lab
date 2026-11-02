#!/usr/bin/env python3
"""R03.51 real-PostgreSQL lease/fencing/retry reference harness.

Uses a disposable schema and PostgreSQL 17 in CI. It is not a production worker.
DATABASE_URL must target a disposable database.
"""
from __future__ import annotations
import json
import os
import random
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import errors

DSN = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stemlab_test")
SCHEMA = "stemlab_r0351_" + uuid.uuid4().hex[:10]
ROLE = "stemlab_r0351_app"

@contextmanager
def admin_conn():
    c = psycopg.connect(DSN, autocommit=True)
    try:
        yield c
    finally:
        c.close()

@contextmanager
def app_conn(tenant="tenant-a"):
    c = psycopg.connect(DSN)
    try:
        with c.transaction():
            c.execute(f"SET LOCAL ROLE {ROLE}")
            c.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
            c.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
            yield c
    finally:
        c.close()

def create_job(conn, job_id, session_id="s1", job_type="validate", max_attempts=3):
    conn.execute(
        """INSERT INTO ingestion_jobs
           (tenant_id,job_id,session_id,package_id,package_version,job_type,status,maximum_attempts)
           VALUES ('tenant-a',%s,%s,'pkg','1.0.0',%s,'queued',%s)""",
        (job_id, session_id, job_type, max_attempts),
    )

def claim_one(conn, worker, lease_seconds=30):
    """Atomic claim; DB clock is authoritative. Returns the new epoch as fencing token."""
    with conn.transaction():
        conn.execute(f"SET LOCAL ROLE {ROLE}")
        conn.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
        conn.execute("SELECT set_config('app.tenant_id','tenant-a',true)")
        while True:
            row = conn.execute(
                """SELECT job_id,status,attempt_count,maximum_attempts,lease_epoch
                   FROM ingestion_jobs
                   WHERE tenant_id='tenant-a' AND (
                     (status IN ('queued','retry') AND available_at <= clock_timestamp())
                     OR (status='running' AND lease_expires_at <= clock_timestamp())
                   )
                   ORDER BY priority DESC, available_at, created_at, job_id
                   LIMIT 1 FOR UPDATE SKIP LOCKED"""
            ).fetchone()
            if row is None:
                return None
            job_id,status,attempts,max_attempts,epoch = row
            if status == "running" and attempts >= max_attempts:
                conn.execute(
                    """UPDATE ingestion_jobs SET status='dead_lettered',lease_owner=NULL,
                         lease_expires_at=NULL,updated_at=clock_timestamp(),
                         last_error_code='LEASE_EXHAUSTED',
                         last_error_safe_message='Lease expired after maximum attempts'
                       WHERE tenant_id='tenant-a' AND job_id=%s""", (job_id,))
                conn.execute(
                    """INSERT INTO ingestion_job_dlq
                       (tenant_id,job_id,terminal_reason,error_code,safe_message,attempt_count,lease_epoch)
                       VALUES ('tenant-a',%s,'max_attempts','LEASE_EXHAUSTED',
                         'Lease expired after maximum attempts',%s,%s)
                       ON CONFLICT (tenant_id,job_id) DO NOTHING""", (job_id,attempts,epoch))
                continue
            next_epoch = epoch + 1
            claimed = conn.execute(
                """UPDATE ingestion_jobs SET status='running',lease_owner=%s,
                     lease_expires_at=clock_timestamp() + (%s * interval '1 second'),
                     lease_epoch=%s,attempt_count=attempt_count+1,updated_at=clock_timestamp()
                   WHERE tenant_id='tenant-a' AND job_id=%s
                   RETURNING job_id,attempt_count,lease_epoch,lease_expires_at""",
                (worker,lease_seconds,next_epoch,job_id),
            ).fetchone()
            return claimed

def renew(conn, job_id, worker, epoch, lease_seconds=30):
    with conn.transaction():
        conn.execute(f"SET LOCAL ROLE {ROLE}")
        conn.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
        conn.execute("SELECT set_config('app.tenant_id','tenant-a',true)")
        row = conn.execute(
            """UPDATE ingestion_jobs SET
                 lease_expires_at=clock_timestamp() + (%s * interval '1 second'),
                 updated_at=clock_timestamp()
               WHERE tenant_id='tenant-a' AND job_id=%s AND status='running'
                 AND lease_owner=%s AND lease_epoch=%s
                 AND lease_expires_at > clock_timestamp()
               RETURNING lease_epoch""", (lease_seconds,job_id,worker,epoch)
        ).fetchone()
        return row is not None

def complete(conn, job_id, worker, epoch, expected_revision=1, fail_outbox=False):
    """Fenced completion and Session/Transition/Outbox writes share one transaction."""
    with conn.transaction():
        conn.execute(f"SET LOCAL ROLE {ROLE}")
        conn.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
        conn.execute("SELECT set_config('app.tenant_id','tenant-a',true)")
        job = conn.execute(
            """SELECT status,lease_owner,lease_epoch,lease_expires_at
               FROM ingestion_jobs WHERE tenant_id='tenant-a' AND job_id=%s FOR UPDATE""",
            (job_id,),
        ).fetchone()
        if job is None:
            raise KeyError(job_id)
        status,owner,current_epoch,expiry = job
        if status == "succeeded" and current_epoch == epoch:
            return "DUPLICATE"
        if not (status == "running" and owner == worker and current_epoch == epoch):
            return "STALE"
        valid = conn.execute(
            "SELECT %s::timestamptz > clock_timestamp()", (expiry,)
        ).fetchone()[0]
        if not valid:
            return "EXPIRED"
        session = conn.execute(
            "SELECT status,revision FROM sessions WHERE tenant_id='tenant-a' AND session_id='s1' FOR UPDATE"
        ).fetchone()
        if session is None or session[1] != expected_revision:
            raise RuntimeError("SESSION_REVISION_CONFLICT")
        next_revision = session[1] + 1
        conn.execute(
            """UPDATE sessions SET status='validated',revision=%s,updated_at=clock_timestamp()
               WHERE tenant_id='tenant-a' AND session_id='s1'""", (next_revision,)
        )
        conn.execute(
            """INSERT INTO transitions
               (tenant_id,session_id,sequence,from_state,to_state,command_id,idempotency_key,
                request_digest,actor_id,expected_revision,resulting_revision)
               VALUES ('tenant-a','s1',%s,%s,'validated',%s,%s,%s,%s,%s,%s)""",
            (next_revision-1,session[0],f"complete-{job_id}-{epoch}",
             f"complete-{job_id}-{epoch}","sha256:"+"a"*64,worker,session[1],next_revision),
        )
        if fail_outbox:
            raise RuntimeError("INJECTED_OUTBOX_FAILURE")
        conn.execute(
            """INSERT INTO outbox(tenant_id,event_id,session_id,sequence,event_type,payload)
               VALUES ('tenant-a',%s,'s1',%s,'package.ingestion.job.completed',%s::jsonb)""",
            (f"job:{job_id}:epoch:{epoch}:completed",next_revision-1,
             json.dumps({"job_id":job_id,"lease_epoch":epoch})),
        )
        conn.execute(
            """UPDATE ingestion_jobs SET status='succeeded',lease_owner=NULL,
                 lease_expires_at=NULL,completed_at=clock_timestamp(),updated_at=clock_timestamp()
               WHERE tenant_id='tenant-a' AND job_id=%s AND lease_epoch=%s""",
            (job_id,epoch),
        )
        return "APPLIED"

def fail_job(conn, job_id, worker, epoch, retryable, error_code="VALIDATION_FAILED",
             safe_message="Package validation failed", delay_seconds=0):
    with conn.transaction():
        conn.execute(f"SET LOCAL ROLE {ROLE}")
        conn.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
        conn.execute("SELECT set_config('app.tenant_id','tenant-a',true)")
        row = conn.execute(
            """SELECT attempt_count,maximum_attempts FROM ingestion_jobs
               WHERE tenant_id='tenant-a' AND job_id=%s AND status='running'
                 AND lease_owner=%s AND lease_epoch=%s
                 AND lease_expires_at > clock_timestamp() FOR UPDATE""",
            (job_id,worker,epoch),
        ).fetchone()
        if row is None:
            return "STALE"
        attempts,max_attempts = row
        dead = (not retryable) or attempts >= max_attempts
        if dead:
            conn.execute(
                """UPDATE ingestion_jobs SET status='dead_lettered',lease_owner=NULL,
                     lease_expires_at=NULL,last_error_code=%s,last_error_safe_message=%s,
                     updated_at=clock_timestamp() WHERE tenant_id='tenant-a' AND job_id=%s""",
                (error_code,safe_message,job_id),
            )
            conn.execute(
                """INSERT INTO ingestion_job_dlq
                   (tenant_id,job_id,terminal_reason,error_code,safe_message,attempt_count,lease_epoch)
                   VALUES ('tenant-a',%s,%s,%s,%s,%s,%s)""",
                (job_id,"non_retryable" if not retryable else "max_attempts",
                 error_code,safe_message,attempts,epoch),
            )
            return "DLQ"
        conn.execute(
            """UPDATE ingestion_jobs SET status='retry',lease_owner=NULL,lease_expires_at=NULL,
                 available_at=clock_timestamp() + (%s * interval '1 second'),
                 last_error_code=%s,last_error_safe_message=%s,updated_at=clock_timestamp()
               WHERE tenant_id='tenant-a' AND job_id=%s""",
            (delay_seconds,error_code,safe_message,job_id),
        )
        return "RETRY"

class WorkerLeasePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = psycopg.connect(DSN,autocommit=True)
        cls.admin.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{ROLE}') "
            f"THEN CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; END IF; END $$"
        )
        cls.admin.execute(f"CREATE SCHEMA {SCHEMA}")
        cls.admin.execute(f"""
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
        """)
        ddl = Path("sql/package-ingestion-worker/R03.51-ingestion-worker.sql").read_text()
        cls.admin.execute(ddl.replace("stemlab_ingest",SCHEMA))
        for table in ("sessions","transitions","outbox","ingestion_jobs","ingestion_job_dlq"):
            cls.admin.execute(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")
            cls.admin.execute(f"ALTER TABLE {SCHEMA}.{table} FORCE ROW LEVEL SECURITY")
            if table not in ("ingestion_jobs","ingestion_job_dlq"):
                cls.admin.execute(
                    f"CREATE POLICY tenant_isolation ON {SCHEMA}.{table} USING "
                    "(tenant_id=current_setting('app.tenant_id',true)) WITH CHECK "
                    "(tenant_id=current_setting('app.tenant_id',true))")
            cls.admin.execute(f"GRANT SELECT,INSERT,UPDATE ON {SCHEMA}.{table} TO {ROLE}")
        cls.admin.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {ROLE}")

    @classmethod
    def tearDownClass(cls):
        cls.admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cls.admin.execute(f"DROP ROLE IF EXISTS {ROLE}")
        cls.admin.close()

    def setUp(self):
        self.admin.execute(f"TRUNCATE {SCHEMA}.ingestion_job_dlq,{SCHEMA}.ingestion_jobs,{SCHEMA}.outbox,{SCHEMA}.transitions,{SCHEMA}.sessions CASCADE")
        self.admin.execute(f"INSERT INTO {SCHEMA}.sessions VALUES ('tenant-a','s1','pkg','1.0.0','quarantined',1,clock_timestamp())")
        with app_conn() as c:
            create_job(c,"j1")

    def test_single_worker_claim_returns_lease_and_epoch(self):
        with app_conn() as c:
            claim = claim_one(c,"worker-a")
        self.assertEqual(claim[2:],(1,1))

    def test_two_workers_cannot_claim_same_job(self):
        barrier=threading.Barrier(2)
        def contender(w):
            barrier.wait()
            with app_conn() as c: return claim_one(c,w)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(contender,("worker-a","worker-b")))
        self.assertEqual(sum(r is not None for r in results),1)

    def test_different_jobs_claim_concurrently(self):
        with app_conn() as c:
            create_job(c,"j2",job_type="scan")
        barrier=threading.Barrier(2)
        def contender(w):
            barrier.wait()
            with app_conn() as c: return claim_one(c,w)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(contender,("worker-a","worker-b")))
        self.assertEqual(len({r[0] for r in results if r}),2)

    def test_expired_lease_is_reclaimed_with_higher_epoch(self):
        with app_conn() as c: first=claim_one(c,"worker-old",lease_seconds=1)
        with app_conn() as c: c.execute("UPDATE ingestion_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE job_id='j1'")
        with app_conn() as c: second=claim_one(c,"worker-new")
        self.assertEqual(second[2],first[2]+1)

    def test_stale_worker_completion_is_rejected_after_reclaim(self):
        with app_conn() as c: old=claim_one(c,"worker-old",lease_seconds=1)
        with app_conn() as c: c.execute("UPDATE ingestion_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE job_id='j1'")
        with app_conn() as c: new=claim_one(c,"worker-new")
        with app_conn() as c: outcome=complete(c,"j1","worker-old",old[2])
        self.assertEqual(outcome,"STALE")
        self.assertEqual(new[2],old[2]+1)

    def test_expired_lease_cannot_complete_before_reclaim(self):
        with app_conn() as c: lease=claim_one(c,"worker-a",lease_seconds=1)
        with app_conn() as c: c.execute("UPDATE ingestion_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE job_id='j1'")
        with app_conn() as c: outcome=complete(c,"j1","worker-a",lease[2])
        self.assertEqual(outcome,"EXPIRED")

    def test_lease_renewal_requires_current_unexpired_epoch(self):
        with app_conn() as c: lease=claim_one(c,"worker-a")
        with app_conn() as c: self.assertTrue(renew(c,"j1","worker-a",lease[2]))
        with app_conn() as c: self.assertFalse(renew(c,"j1","worker-a",lease[2]+1))

    def test_completion_atomically_updates_session_transition_outbox_and_job(self):
        with app_conn() as c: lease=claim_one(c,"worker-a")
        with app_conn() as c: self.assertEqual(complete(c,"j1","worker-a",lease[2]),"APPLIED")
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.sessions").fetchone()[0],"validated")
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.ingestion_jobs").fetchone()[0],"succeeded")
        self.assertEqual(self.admin.execute(f"SELECT count(*) FROM {SCHEMA}.transitions").fetchone()[0],1)
        self.assertEqual(self.admin.execute(f"SELECT count(*) FROM {SCHEMA}.outbox").fetchone()[0],1)

    def test_outbox_failure_rolls_back_completion_and_session(self):
        with app_conn() as c: lease=claim_one(c,"worker-a")
        with self.assertRaises(RuntimeError):
            with app_conn() as c: complete(c,"j1","worker-a",lease[2],fail_outbox=True)
        self.assertEqual(self.admin.execute(f"SELECT status,revision FROM {SCHEMA}.sessions").fetchone(),("quarantined",1))
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.ingestion_jobs").fetchone()[0],"running")
        self.assertEqual(self.admin.execute(f"SELECT count(*) FROM {SCHEMA}.outbox").fetchone()[0],0)

    def test_retryable_failure_schedules_retry(self):
        with app_conn() as c: lease=claim_one(c,"worker-a")
        with app_conn() as c: result=fail_job(c,"j1","worker-a",lease[2],True,delay_seconds=0)
        self.assertEqual(result,"RETRY")
        self.assertEqual(self.admin.execute(f"SELECT status,attempt_count FROM {SCHEMA}.ingestion_jobs").fetchone(),("retry",1))

    def test_non_retryable_failure_enters_dlq(self):
        with app_conn() as c: lease=claim_one(c,"worker-a")
        with app_conn() as c: result=fail_job(c,"j1","worker-a",lease[2],False)
        self.assertEqual(result,"DLQ")
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.ingestion_jobs").fetchone()[0],"dead_lettered")
        self.assertEqual(self.admin.execute(f"SELECT count(*) FROM {SCHEMA}.ingestion_job_dlq").fetchone()[0],1)

    def test_maximum_attempts_prevents_another_retry(self):
        with app_conn() as c:
            c.execute("UPDATE ingestion_jobs SET maximum_attempts=1 WHERE job_id='j1'")
            lease=claim_one(c,"worker-a")
        with app_conn() as c: self.assertEqual(fail_job(c,"j1","worker-a",lease[2],True),"DLQ")

    def test_duplicate_completion_has_no_second_effect(self):
        with app_conn() as c: lease=claim_one(c,"worker-a")
        with app_conn() as c: self.assertEqual(complete(c,"j1","worker-a",lease[2]),"APPLIED")
        with app_conn() as c: self.assertEqual(complete(c,"j1","worker-a",lease[2]),"DUPLICATE")
        self.assertEqual(self.admin.execute(f"SELECT count(*) FROM {SCHEMA}.outbox").fetchone()[0],1)

    def test_rls_blocks_cross_tenant_job_reads(self):
        self.admin.execute(f"INSERT INTO {SCHEMA}.sessions VALUES ('tenant-b','s1','pkg','1.0.0','quarantined',1,clock_timestamp())")
        self.admin.execute(f"INSERT INTO {SCHEMA}.ingestion_jobs(tenant_id,job_id,session_id,package_id,package_version,job_type,status) VALUES ('tenant-b','jb','s1','pkg','1.0.0','validate','queued')")
        with app_conn("tenant-a") as c:
            self.assertEqual(c.execute("SELECT count(*) FROM ingestion_jobs").fetchone()[0],1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
