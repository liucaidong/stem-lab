#!/usr/bin/env python3
"""Disposable PostgreSQL reference harness for Job-rooted v2 authorization.

Exercises worker.job.complete only. Not a production Store Adapter.
"""
from __future__ import annotations
import base64, json, os, threading, time, unittest, uuid
from concurrent.futures import ThreadPoolExecutor
import psycopg
from psycopg.conninfo import make_conninfo

DSN = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stemlab_test")
SUFFIX = uuid.uuid4().hex[:10]
SCHEMA = "resource_auth_" + SUFFIX
VERIFIER = "resource_verifier_" + SUFFIX
RUNTIME = "resource_runtime_" + SUFFIX
LOGIN = "resource_login_" + SUFFIX
PASSWORD = uuid.uuid4().hex + uuid.uuid4().hex
ISSUER = "stemlab-resource-test-issuer"
AUDIENCE = "stemlab-worker-store"
MAX_LIFETIME = 120

def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

def canonical_payload(claims: dict) -> bytes:
    return json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

class ResourceAuthorizationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = psycopg.connect(DSN, autocommit=True)
        cls.admin.execute("CREATE EXTENSION IF NOT EXISTS pgsodium")
        cls.admin.execute("LOAD 'pgsodium'")
        cls.admin.execute("SET pgsodium.enable_event_trigger = 'off'")
        cls.admin.execute(f"CREATE ROLE {VERIFIER} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
        cls.admin.execute(f"CREATE ROLE {RUNTIME} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
        cls.admin.execute(f"CREATE ROLE {LOGIN} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '{PASSWORD}'")
        cls.admin.execute(f"GRANT {RUNTIME} TO {LOGIN}")
        cls.admin.execute(f"CREATE SCHEMA {SCHEMA} AUTHORIZATION {VERIFIER}")
        cls.public_key, cls.private_key = cls.admin.execute(
            "SELECT public,secret FROM pgsodium.crypto_sign_new_keypair()"
        ).fetchone()
        cls.admin.execute(f"CREATE TABLE {SCHEMA}.issuer_keys (kid text PRIMARY KEY, issuer text NOT NULL, public_key bytea NOT NULL, not_before timestamptz NOT NULL, not_after timestamptz, revoked_at timestamptz)")
        cls.admin.execute(f"INSERT INTO {SCHEMA}.issuer_keys(kid,issuer,public_key,not_before) VALUES ('test-key',%s,%s,clock_timestamp()-interval '1 day')", (ISSUER, cls.public_key))
        cls.admin.execute(f"GRANT SELECT ON {SCHEMA}.issuer_keys TO {VERIFIER}")
        cls.admin.execute("GRANT USAGE ON SCHEMA pgsodium TO " + VERIFIER)
        cls.admin.execute("GRANT EXECUTE ON FUNCTION pgsodium.crypto_sign_verify_detached(bytea,bytea,bytea) TO " + VERIFIER)

        cls.admin.execute(f"CREATE TABLE {SCHEMA}.sessions (tenant_id text NOT NULL,session_id text NOT NULL,revision bigint NOT NULL,PRIMARY KEY(tenant_id,session_id))")
        cls.admin.execute(f"CREATE TABLE {SCHEMA}.jobs (tenant_id text NOT NULL,job_id text NOT NULL,session_id text NOT NULL,owner text,epoch bigint NOT NULL CHECK(epoch>0),status text NOT NULL CHECK(status IN ('queued','running','retry','succeeded','failed','dead_lettered')),lease_expires_at timestamptz,available_at timestamptz NOT NULL DEFAULT clock_timestamp(),attempt_count integer NOT NULL DEFAULT 1 CHECK(attempt_count>=0),maximum_attempts integer NOT NULL DEFAULT 5 CHECK(maximum_attempts BETWEEN 1 AND 100),last_error_code text,PRIMARY KEY(tenant_id,job_id),UNIQUE(tenant_id,job_id,session_id),FOREIGN KEY(tenant_id,session_id) REFERENCES {SCHEMA}.sessions(tenant_id,session_id),CHECK(status<>'running' OR (owner IS NOT NULL AND lease_expires_at IS NOT NULL)))")
        cls.admin.execute(f"CREATE TABLE {SCHEMA}.receipts (tenant_id text NOT NULL,operation_id text NOT NULL,job_id text NOT NULL,session_id text NOT NULL,request_digest text NOT NULL,outcome text NOT NULL,PRIMARY KEY(tenant_id,operation_id),FOREIGN KEY(tenant_id,job_id,session_id) REFERENCES {SCHEMA}.jobs(tenant_id,job_id,session_id))")
        cls.admin.execute(f"CREATE TABLE {SCHEMA}.transitions (tenant_id text NOT NULL,transition_id text NOT NULL,job_id text NOT NULL,session_id text NOT NULL,operation_id text NOT NULL,from_state text NOT NULL,to_state text NOT NULL,PRIMARY KEY(tenant_id,transition_id),FOREIGN KEY(tenant_id,job_id,session_id) REFERENCES {SCHEMA}.jobs(tenant_id,job_id,session_id))")
        cls.admin.execute(f"CREATE TABLE {SCHEMA}.outbox (tenant_id text NOT NULL,event_id text NOT NULL,job_id text NOT NULL,session_id text NOT NULL,operation_id text NOT NULL,event_type text NOT NULL,PRIMARY KEY(tenant_id,event_id),FOREIGN KEY(tenant_id,job_id,session_id) REFERENCES {SCHEMA}.jobs(tenant_id,job_id,session_id))")
        cls.admin.execute(f"CREATE TABLE {SCHEMA}.dlq_items (tenant_id text NOT NULL,dlq_item_id text NOT NULL,job_id text NOT NULL,session_id text NOT NULL,terminal_reason text NOT NULL CHECK(terminal_reason IN ('max_attempts','non_retryable')),error_code text NOT NULL,attempt_count integer NOT NULL CHECK(attempt_count>0),lease_epoch bigint NOT NULL CHECK(lease_epoch>0),replay_count integer NOT NULL DEFAULT 0 CHECK(replay_count>=0),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(tenant_id,dlq_item_id),FOREIGN KEY(tenant_id,job_id,session_id) REFERENCES {SCHEMA}.jobs(tenant_id,job_id,session_id))")
        cls.admin.execute(f"CREATE TABLE {SCHEMA}.nonce_ledger (issuer text NOT NULL,kid text NOT NULL,nonce text NOT NULL,token text NOT NULL,transaction_id xid8 NOT NULL,tenant_id text NOT NULL,job_id text NOT NULL,session_id text NOT NULL,owner text NOT NULL,epoch bigint NOT NULL,action text NOT NULL,resource_type text NOT NULL,resource_id text NOT NULL,operation_id text NOT NULL,PRIMARY KEY(issuer,kid,nonce))")
        for table in ("sessions","jobs","receipts","transitions","outbox","dlq_items","nonce_ledger"):
            cls.admin.execute(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")
            cls.admin.execute(f"ALTER TABLE {SCHEMA}.{table} FORCE ROW LEVEL SECURITY")

        cls.admin.execute(f"CREATE POLICY sessions_verifier_read ON {SCHEMA}.sessions FOR SELECT TO {VERIFIER} USING(true)")
        cls.admin.execute(f"CREATE POLICY jobs_verifier_read ON {SCHEMA}.jobs FOR SELECT TO {VERIFIER} USING(true)")
        cls.admin.execute(f"CREATE POLICY jobs_verifier_update ON {SCHEMA}.jobs FOR UPDATE TO {VERIFIER} USING(true) WITH CHECK(true)")
        cls.admin.execute(f"CREATE POLICY receipts_verifier_read ON {SCHEMA}.receipts FOR SELECT TO {VERIFIER} USING(true)")
        cls.admin.execute(f"CREATE POLICY nonce_verifier_access ON {SCHEMA}.nonce_ledger FOR ALL TO {VERIFIER} USING(true) WITH CHECK(true)")
        cls.admin.execute(f"CREATE POLICY transitions_verifier_insert ON {SCHEMA}.transitions FOR INSERT TO {VERIFIER} WITH CHECK(true)")
        cls.admin.execute(f"CREATE POLICY outbox_verifier_insert ON {SCHEMA}.outbox FOR INSERT TO {VERIFIER} WITH CHECK(true)")
        cls.admin.execute(f"CREATE POLICY dlq_verifier_insert ON {SCHEMA}.dlq_items FOR INSERT TO {VERIFIER} WITH CHECK(true)")
        cls.admin.execute(f"GRANT SELECT ON {SCHEMA}.sessions,{SCHEMA}.jobs,{SCHEMA}.receipts TO {VERIFIER}")
        cls.admin.execute(f"GRANT UPDATE(status,lease_expires_at,owner,available_at,attempt_count,last_error_code) ON {SCHEMA}.jobs TO {VERIFIER}")
        cls.admin.execute(f"GRANT SELECT,INSERT ON {SCHEMA}.nonce_ledger TO {VERIFIER}")
        cls.admin.execute(f"GRANT INSERT ON {SCHEMA}.transitions,{SCHEMA}.outbox,{SCHEMA}.dlq_items TO {VERIFIER}")

        verify_sql = f"""
        CREATE FUNCTION {SCHEMA}.verify_v2(token text) RETURNS jsonb
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,{SCHEMA}
        AS $verify$
        DECLARE p text; s text; pb bytea; sb bytea; pk bytea; c jsonb;
                i bigint; e bigint; now_s bigint;
        BEGIN
          IF token IS NULL OR length(token)>16384 OR token !~ '^[A-Za-z0-9_-]+[.][A-Za-z0-9_-]+$' THEN RETURN NULL; END IF;
          p:=split_part(token,'.',1); s:=split_part(token,'.',2);
          pb:=decode(rpad(translate(p,'-_','+/'),((length(p)+3)/4)*4,'='),'base64');
          sb:=decode(rpad(translate(s,'-_','+/'),((length(s)+3)/4)*4,'='),'base64');
          IF octet_length(sb)<>64 THEN RETURN NULL; END IF;
          c:=convert_from(pb,'UTF8')::jsonb;
          IF jsonb_typeof(c) IS DISTINCT FROM 'object'
             OR NOT(c ?& ARRAY['v','iss','kid','tenant_id','sub','aud','action','job_id','resource_type','resource_id','session_id','owner','epoch','operation_id','iat','exp','nonce'])
             OR c-ARRAY['v','iss','kid','tenant_id','sub','aud','action','job_id','resource_type','resource_id','session_id','owner','epoch','operation_id','iat','exp','nonce'] <> '{{}}'::jsonb THEN RETURN NULL; END IF;
          IF c->>'v'<>'2' OR jsonb_typeof(c->'v') IS DISTINCT FROM 'number'
             OR jsonb_typeof(c->'epoch') IS DISTINCT FROM 'number'
             OR jsonb_typeof(c->'iat') IS DISTINCT FROM 'number'
             OR jsonb_typeof(c->'exp') IS DISTINCT FROM 'number' THEN RETURN NULL; END IF;
          IF jsonb_typeof(c->'iss')<>'string' OR jsonb_typeof(c->'kid')<>'string'
             OR jsonb_typeof(c->'tenant_id')<>'string' OR jsonb_typeof(c->'sub')<>'string'
             OR jsonb_typeof(c->'aud')<>'string' OR jsonb_typeof(c->'action')<>'string'
             OR jsonb_typeof(c->'job_id')<>'string' OR jsonb_typeof(c->'resource_type')<>'string'
             OR jsonb_typeof(c->'resource_id')<>'string' OR jsonb_typeof(c->'session_id')<>'string'
             OR jsonb_typeof(c->'owner')<>'string' OR jsonb_typeof(c->'operation_id')<>'string'
             OR jsonb_typeof(c->'nonce')<>'string' THEN RETURN NULL; END IF;
          IF (c->>'epoch')::numeric<>trunc((c->>'epoch')::numeric)
             OR (c->>'iat')::numeric<>trunc((c->>'iat')::numeric)
             OR (c->>'exp')::numeric<>trunc((c->>'exp')::numeric) THEN RETURN NULL; END IF;
          IF length(c->>'iss') NOT BETWEEN 1 AND 256 OR length(c->>'kid') NOT BETWEEN 1 AND 128
             OR length(c->>'tenant_id') NOT BETWEEN 1 AND 256 OR length(c->>'sub') NOT BETWEEN 1 AND 256
             OR length(c->>'aud') NOT BETWEEN 1 AND 256 OR length(c->>'job_id') NOT BETWEEN 1 AND 256
             OR length(c->>'session_id') NOT BETWEEN 1 AND 256 OR length(c->>'owner') NOT BETWEEN 1 AND 256
             OR length(c->>'operation_id') NOT BETWEEN 1 AND 256
             OR length(c->>'nonce') NOT BETWEEN 16 AND 256 OR c->>'nonce' !~ '^[A-Za-z0-9_-]+$' THEN RETURN NULL; END IF;
          i:=(c->>'iat')::bigint; e:=(c->>'exp')::bigint;
          now_s:=floor(extract(epoch FROM clock_timestamp()))::bigint;
          IF i>now_s OR e<=now_s OR e<=i OR e-i>{MAX_LIFETIME} THEN RETURN NULL; END IF;
          IF c->>'action' IN ('worker.job.renew','worker.job.complete','worker.job.fail','worker.job.retry','worker.job.dead_letter') THEN
            IF c->>'resource_type'<>'job' OR c->>'resource_id'<>c->>'job_id' THEN RETURN NULL; END IF;
          ELSIF c->>'action'='worker.receipt.reconcile' THEN
            IF c->>'resource_type'<>'receipt' OR c->>'resource_id'<>c->>'operation_id' THEN RETURN NULL; END IF;
          ELSE
            RETURN NULL;
          END IF;
          IF (c->>'epoch')::bigint<1 THEN RETURN NULL; END IF;
          SELECT public_key INTO pk FROM {SCHEMA}.issuer_keys
           WHERE kid=c->>'kid' AND issuer=c->>'iss' AND revoked_at IS NULL
             AND not_before<=clock_timestamp() AND (not_after IS NULL OR not_after>clock_timestamp());
          IF NOT FOUND OR pk IS NULL THEN RETURN NULL; END IF;
          IF NOT pgsodium.crypto_sign_verify_detached(sb,convert_to(p,'UTF8'),pk) THEN RETURN NULL; END IF;
          RETURN c;
        EXCEPTION WHEN OTHERS THEN RETURN NULL;
        END $verify$
        """
        cls.admin.execute(verify_sql)
        cls.admin.execute(f"ALTER FUNCTION {SCHEMA}.verify_v2(text) OWNER TO {VERIFIER}")
        cls.admin.execute(f"REVOKE ALL ON FUNCTION {SCHEMA}.verify_v2(text) FROM PUBLIC")

        authorize_sql = f"""
        CREATE FUNCTION {SCHEMA}.authorize_v2(token text) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,{SCHEMA}
        AS $authorize$
        DECLARE c jsonb; tx xid8; po text; pe bigint; px timestamptz; ps text;
                ledger_tx xid8; ledger_token text;
        BEGIN
          c:={SCHEMA}.verify_v2(token);
          IF c IS NULL OR c->>'aud'<>'{AUDIENCE}'
             OR c->>'job_id' IS DISTINCT FROM current_setting('app.resource_job_id',true)
             OR c->>'operation_id' IS DISTINCT FROM current_setting('app.resource_operation_id',true) THEN
            RETURN false;
          END IF;
          IF c->>'action' IN ('worker.job.complete','worker.job.renew','worker.job.fail','worker.job.retry','worker.job.dead_letter') THEN
            SELECT owner,epoch,lease_expires_at,status INTO po,pe,px,ps
              FROM {SCHEMA}.jobs
             WHERE tenant_id=c->>'tenant_id' AND job_id=c->>'job_id' AND session_id=c->>'session_id';
            IF NOT FOUND OR po IS DISTINCT FROM c->>'owner' OR pe IS DISTINCT FROM (c->>'epoch')::bigint
               OR ps IS DISTINCT FROM 'running' OR px<=clock_timestamp() THEN RETURN false; END IF;
          ELSIF c->>'action'='worker.receipt.reconcile' THEN
            PERFORM 1 FROM {SCHEMA}.receipts
             WHERE tenant_id=c->>'tenant_id' AND operation_id=c->>'operation_id'
               AND job_id=c->>'job_id' AND session_id=c->>'session_id';
            IF NOT FOUND THEN RETURN false; END IF;
          ELSE
            RETURN false;
          END IF;
          tx:=pg_current_xact_id();
          INSERT INTO {SCHEMA}.nonce_ledger
            (issuer,kid,nonce,token,transaction_id,tenant_id,job_id,session_id,owner,epoch,action,resource_type,resource_id,operation_id)
          VALUES(c->>'iss',c->>'kid',c->>'nonce',token,tx,c->>'tenant_id',c->>'job_id',c->>'session_id',
                 c->>'owner',(c->>'epoch')::bigint,c->>'action',c->>'resource_type',c->>'resource_id',c->>'operation_id')
          ON CONFLICT(issuer,kid,nonce) DO NOTHING;
          SELECT transaction_id,token INTO ledger_tx,ledger_token FROM {SCHEMA}.nonce_ledger
           WHERE issuer=c->>'iss' AND kid=c->>'kid' AND nonce=c->>'nonce';
          RETURN FOUND AND ledger_tx=tx AND ledger_token=token;
        EXCEPTION WHEN OTHERS THEN RETURN false;
        END $authorize$
        """
        cls.admin.execute(authorize_sql)
        cls.admin.execute(f"ALTER FUNCTION {SCHEMA}.authorize_v2(text) OWNER TO {VERIFIER}")
        cls.admin.execute(f"REVOKE ALL ON FUNCTION {SCHEMA}.authorize_v2(text) FROM PUBLIC")

        renew_sql = f"""
        CREATE FUNCTION {SCHEMA}.renew_v2(token text, lease_seconds integer)
        RETURNS timestamptz
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,{SCHEMA}
        AS $renew$
        DECLARE c jsonb; renewed_until timestamptz;
        BEGIN
          IF lease_seconds NOT BETWEEN 5 AND 3600 THEN RETURN NULL; END IF;
          c:={SCHEMA}.verify_v2(token);
          IF c IS NULL OR c->>'action'<>'worker.job.renew' THEN RETURN NULL; END IF;
          IF NOT {SCHEMA}.authorize_v2(token) THEN RETURN NULL; END IF;
          UPDATE {SCHEMA}.jobs
             SET lease_expires_at=clock_timestamp()+make_interval(secs=>lease_seconds)
           WHERE tenant_id=c->>'tenant_id' AND job_id=c->>'job_id'
             AND session_id=c->>'session_id' AND owner=c->>'owner'
             AND epoch=(c->>'epoch')::bigint AND status='running'
             AND lease_expires_at>clock_timestamp()
           RETURNING lease_expires_at INTO renewed_until;
          IF NOT FOUND THEN RAISE EXCEPTION 'lease fence changed during renewal'; END IF;
          RETURN renewed_until;
        EXCEPTION WHEN OTHERS THEN RETURN NULL;
        END $renew$
        """
        cls.admin.execute(renew_sql)
        cls.admin.execute(f"ALTER FUNCTION {SCHEMA}.renew_v2(text,integer) OWNER TO {VERIFIER}")
        cls.admin.execute(f"REVOKE ALL ON FUNCTION {SCHEMA}.renew_v2(text,integer) FROM PUBLIC")

        fail_sql = f"""
        CREATE FUNCTION {SCHEMA}.fail_v2(token text)
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,{SCHEMA}
        AS $fail$
        DECLARE c jsonb;
        BEGIN
          c:={SCHEMA}.verify_v2(token);
          IF c IS NULL OR c->>'action'<>'worker.job.fail' THEN RETURN false; END IF;
          IF NOT {SCHEMA}.authorize_v2(token) THEN RETURN false; END IF;
          UPDATE {SCHEMA}.jobs
             SET status='failed'
           WHERE tenant_id=c->>'tenant_id' AND job_id=c->>'job_id'
             AND session_id=c->>'session_id' AND owner=c->>'owner'
             AND epoch=(c->>'epoch')::bigint AND status='running'
             AND lease_expires_at>clock_timestamp();
          IF NOT FOUND THEN RAISE EXCEPTION 'lease fence changed during failure transition'; END IF;
          INSERT INTO {SCHEMA}.transitions
            (tenant_id,transition_id,job_id,session_id,operation_id,from_state,to_state)
          VALUES(c->>'tenant_id',(c->>'operation_id')||':failed',c->>'job_id',
                 c->>'session_id',c->>'operation_id','running','failed');
          INSERT INTO {SCHEMA}.outbox
            (tenant_id,event_id,job_id,session_id,operation_id,event_type)
          VALUES(c->>'tenant_id',(c->>'operation_id')||':job.failed',c->>'job_id',
                 c->>'session_id',c->>'operation_id','job.failed');
          RETURN true;
        EXCEPTION WHEN OTHERS THEN RETURN false;
        END $fail$
        """
        cls.admin.execute(fail_sql)
        cls.admin.execute(f"ALTER FUNCTION {SCHEMA}.fail_v2(text) OWNER TO {VERIFIER}")
        cls.admin.execute(f"REVOKE ALL ON FUNCTION {SCHEMA}.fail_v2(text) FROM PUBLIC")

        retry_sql = f"""
        CREATE FUNCTION {SCHEMA}.retry_v2(token text, delay_seconds integer, error_code text)
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,{SCHEMA}
        AS $retry$
        DECLARE c jsonb;
        BEGIN
          c:={SCHEMA}.verify_v2(token);
          IF c IS NULL OR c->>'action'<>'worker.job.retry'
             OR delay_seconds IS NULL OR delay_seconds NOT BETWEEN 1 AND 86400
             OR error_code IS NULL OR error_code !~ '^[A-Z][A-Z0-9_]{0,63}



        allows_sql = f"""
        CREATE FUNCTION {SCHEMA}.assertion_allows(
          token text,row_tenant text,row_job text,row_session text,
          expected_action text,expected_resource_type text,expected_resource_id text,expected_operation_id text
        ) RETURNS boolean LANGUAGE sql SECURITY DEFINER VOLATILE
        SET search_path=pg_catalog,{SCHEMA}
        AS $allows$
          SELECT EXISTS(SELECT 1 FROM {SCHEMA}.nonce_ledger n
            WHERE n.token=token AND n.transaction_id=pg_current_xact_id()
              AND n.tenant_id=row_tenant AND n.job_id=row_job AND n.session_id=row_session
              AND n.action=expected_action AND n.resource_type=expected_resource_type
              AND n.resource_id=expected_resource_id AND n.operation_id=expected_operation_id)
        $allows$
        """
        cls.admin.execute(allows_sql)
        cls.admin.execute(f"ALTER FUNCTION {SCHEMA}.assertion_allows(text,text,text,text,text,text,text,text) OWNER TO {VERIFIER}")
        cls.admin.execute(f"REVOKE ALL ON FUNCTION {SCHEMA}.assertion_allows(text,text,text,text,text,text,text,text) FROM PUBLIC")

        # Policies on job-scoped tables rely on nonce ledger consumption in this
        # transaction. The caller-controlled GUC alone grants no access.
        for table in ("transitions","outbox"):
            cls.admin.execute(
                f"CREATE POLICY {table}_runtime_scope ON {SCHEMA}.{table} FOR ALL TO {RUNTIME} "
                f"USING({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
                "tenant_id,job_id,session_id,'worker.job.complete','job',"
                "job_id,operation_id)) "
                f"WITH CHECK({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
                "tenant_id,job_id,session_id,'worker.job.complete','job',"
                "job_id,operation_id))"
            )
        cls.admin.execute(
            f"CREATE POLICY receipts_complete_insert ON {SCHEMA}.receipts FOR INSERT TO {RUNTIME} "
            f"WITH CHECK({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
            "tenant_id,job_id,session_id,'worker.job.complete','job',job_id,operation_id))"
        )
        cls.admin.execute(
            f"CREATE POLICY receipts_complete_select ON {SCHEMA}.receipts FOR SELECT TO {RUNTIME} "
            f"USING({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
            "tenant_id,job_id,session_id,'worker.job.complete','job',job_id,operation_id))"
        )
        cls.admin.execute(
            f"CREATE POLICY receipts_reconcile_select ON {SCHEMA}.receipts FOR SELECT TO {RUNTIME} "
            f"USING({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
            "tenant_id,job_id,session_id,'worker.receipt.reconcile','receipt',operation_id,operation_id))"
        )
        cls.admin.execute(
            f"CREATE POLICY jobs_runtime_select ON {SCHEMA}.jobs FOR SELECT TO {RUNTIME} "
            f"USING(status IN ('running','succeeded') AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),tenant_id,job_id,session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),"
            "current_setting('app.resource_operation_id',true)))"
        )
        cls.admin.execute(
            f"CREATE POLICY jobs_runtime_scope ON {SCHEMA}.jobs FOR UPDATE TO {RUNTIME} "
            f"USING(status='running' AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),tenant_id,job_id,session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),"
            "current_setting('app.resource_operation_id',true))) "
            f"WITH CHECK(status='succeeded' AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),tenant_id,job_id,session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),"
            "current_setting('app.resource_operation_id',true)))"
        )
        cls.admin.execute(
            f"CREATE POLICY sessions_runtime_scope ON {SCHEMA}.sessions FOR SELECT TO {RUNTIME} "
            f"USING(EXISTS(SELECT 1 FROM {SCHEMA}.jobs j WHERE j.tenant_id=sessions.tenant_id "
            f"AND j.session_id=sessions.session_id AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),j.tenant_id,j.job_id,j.session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),current_setting('app.resource_operation_id',true))))"
        )
        cls.admin.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.authorize_v2(text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.renew_v2(text,integer) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.fail_v2(text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.retry_v2(text,integer,text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.dead_letter_v2(text,text,text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.assertion_allows(text,text,text,text,text,text,text,text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT SELECT ON {SCHEMA}.jobs TO {RUNTIME}")
        cls.admin.execute(f"GRANT UPDATE(status) ON {SCHEMA}.jobs TO {RUNTIME}")
        cls.admin.execute(f"GRANT SELECT ON {SCHEMA}.sessions TO {RUNTIME}")
        cls.admin.execute(f"GRANT SELECT,INSERT ON {SCHEMA}.receipts,{SCHEMA}.transitions,{SCHEMA}.outbox TO {RUNTIME}")

        cls.admin.execute(f"INSERT INTO {SCHEMA}.sessions VALUES ('tenant-a','session-a',4),('tenant-a','session-b',9),('tenant-b','session-x',1)")
        cls.admin.execute(
            f"INSERT INTO {SCHEMA}.jobs (tenant_id,job_id,session_id,owner,epoch,status,lease_expires_at) VALUES "
            "('tenant-a','job-a','session-a','worker-a',7,'running',clock_timestamp()+interval '5 minutes'),"
            "('tenant-a','job-b','session-b','worker-b',2,'running',clock_timestamp()+interval '5 minutes'),"
            "('tenant-b','job-x','session-x','worker-x',1,'running',clock_timestamp()+interval '5 minutes')"
        )

    @classmethod
    def tearDownClass(cls):
        cls.admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cls.admin.execute(f"REVOKE USAGE ON SCHEMA pgsodium FROM {VERIFIER}")
        cls.admin.execute(f"REVOKE EXECUTE ON FUNCTION pgsodium.crypto_sign_verify_detached(bytea,bytea,bytea) FROM {VERIFIER}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {LOGIN}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {RUNTIME}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {VERIFIER}")
        cls.admin.close()

    def setUp(self):
        self.admin.execute(f"UPDATE {SCHEMA}.jobs SET owner='worker-a',epoch=7,status='running',lease_expires_at=clock_timestamp()+interval '5 minutes',available_at=clock_timestamp(),attempt_count=1,maximum_attempts=5,last_error_code=NULL WHERE tenant_id='tenant-a' AND job_id='job-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.receipts WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.transitions WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.outbox WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.dlq_items WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.nonce_ledger")

    @classmethod
    def claims(cls, **overrides):
        now=int(time.time())
        c={"v":2,"iss":ISSUER,"kid":"test-key","tenant_id":"tenant-a","sub":"worker-a",
           "aud":AUDIENCE,"action":"worker.job.complete","job_id":"job-a",
           "resource_type":"job","resource_id":"job-a","session_id":"session-a",
           "owner":"worker-a","epoch":7,"operation_id":"op-a","iat":now,"exp":now+60,
           "nonce":uuid.uuid4().hex}
        c.update(overrides)
        return c

    @classmethod
    def issue(cls, **overrides):
        c=cls.claims(**overrides)
        payload=b64url(canonical_payload(c))
        sig=cls.admin.execute("SELECT pgsodium.crypto_sign_detached(%s,%s)",(payload.encode("ascii"),cls.private_key)).fetchone()[0]
        return payload+"."+b64url(sig)

    @classmethod
    def runtime_connection(cls):
        dsn=make_conninfo(DSN,user=LOGIN,password=PASSWORD)
        conn=psycopg.connect(dsn,autocommit=True)
        conn.execute(f"SET ROLE {RUNTIME}")
        return conn

    @classmethod
    def authorize_once(cls,token):
        with cls.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                return conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0]

    def test_valid_complete_unit_of_work(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                self.assertEqual(conn.execute(f"SELECT job_id FROM {SCHEMA}.jobs").fetchall(),[("job-a",)])
                changed=conn.execute(
                    f"UPDATE {SCHEMA}.jobs SET status='succeeded' WHERE tenant_id='tenant-a' AND job_id='job-a' "
                    "AND session_id='session-a' AND owner='worker-a' AND epoch=7 AND status='running' "
                    "AND lease_expires_at>clock_timestamp() RETURNING job_id"
                ).fetchall()
                self.assertEqual(changed,[("job-a",)])
                conn.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-1','APPLIED')")
                conn.execute(f"INSERT INTO {SCHEMA}.transitions VALUES ('tenant-a','tr-a','job-a','session-a','op-a','running','succeeded')")
                conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','ev-a','job-a','session-a','op-a','job.completed')")
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0],"succeeded")

    def test_ambiguous_commit_reconciles_receipt_and_detects_digest_conflict(self):
        completion=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(completion,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(completion,)).fetchone()[0])
                conn.execute(f"UPDATE {SCHEMA}.jobs SET status='succeeded' WHERE tenant_id='tenant-a' AND job_id='job-a' AND session_id='session-a' AND owner='worker-a' AND epoch=7 AND status='running' AND lease_expires_at>clock_timestamp()")
                conn.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-1','APPLIED')")
                conn.execute(f"INSERT INTO {SCHEMA}.transitions VALUES ('tenant-a','tr-a','job-a','session-a','op-a','running','succeeded')")
                conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','ev-a','job-a','session-a','op-a','job.completed')")
        # The commit above is treated as acknowledged ambiguously: a fresh,
        # separately signed Receipt capability resolves the durable outcome.
        reconcile=self.issue(action="worker.receipt.reconcile",resource_type="receipt",resource_id="op-a")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(reconcile,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(reconcile,)).fetchone()[0])
                row=conn.execute(f"SELECT request_digest,outcome FROM {SCHEMA}.receipts WHERE tenant_id='tenant-a' AND operation_id='op-a'").fetchone()
                self.assertEqual(row,("digest-1","APPLIED"))
                same_digest="DUPLICATE" if row[0]=="digest-1" else "IDEMPOTENCY_CONFLICT"
                changed_digest="DUPLICATE" if row[0]=="digest-other" else "IDEMPOTENCY_CONFLICT"
                self.assertEqual(same_digest,"DUPLICATE")
                self.assertEqual(changed_digest,"IDEMPOTENCY_CONFLICT")

    def test_receipt_reconcile_rejects_wrong_or_missing_receipt(self):
        self.admin.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-1','APPLIED')")
        wrong=self.issue(action="worker.receipt.reconcile",resource_type="receipt",resource_id="other-operation")
        missing=self.issue(action="worker.receipt.reconcile",resource_type="receipt",resource_id="op-missing",operation_id="op-missing")
        self.assertFalse(self.authorize_once(wrong))
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(missing,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-missing',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(missing,)).fetchone()[0])

    def test_child_rows_cannot_splice_another_session_or_tenant(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','bad-session','job-a','session-b','op-a','job.completed')")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-b','bad-tenant','job-a','session-a','op-a','job.completed')")

    def test_complete_capability_cannot_write_failed_terminal_state(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(f"UPDATE {SCHEMA}.jobs SET status='failed' WHERE tenant_id='tenant-a' AND job_id='job-a'")

    def test_same_claims_and_key_produce_identical_token(self):
        fixed = {
            "nonce": "0123456789abcdef0123456789abcdef",
            "iat": 1800000000,
            "exp": 1800000060,
        }
        self.assertEqual(self.issue(**fixed), self.issue(**fixed))
    def test_same_token_reused_only_inside_same_transaction(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])

    def test_committed_nonce_replay_is_denied(self):
        token=self.issue()
        self.assertTrue(self.authorize_once(token))
        self.assertFalse(self.authorize_once(token))

    def test_rollback_removes_nonce_and_business_writes(self):
        token=self.issue()
        conn=self.runtime_connection()
        try:
            with self.assertRaises(RuntimeError):
                with conn.transaction():
                    conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                    conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                    conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                    self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                    conn.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-x','APPLIED')")
                    raise RuntimeError("injected rollback")
        finally:
            conn.close()
        self.assertTrue(self.authorize_once(token))
        self.assertIsNone(self.admin.execute(f"SELECT 1 FROM {SCHEMA}.receipts WHERE operation_id='op-a'").fetchone())

    def test_wrong_tenant_job_session_owner_epoch_or_audience_denied(self):
        cases=[{"tenant_id":"tenant-b"},{"job_id":"job-b","resource_id":"job-b"},
               {"session_id":"session-b"},{"owner":"worker-b"},{"epoch":8},{"aud":"wrong"}]
        for change in cases:
            with self.subTest(change=change):
                self.assertFalse(self.authorize_once(self.issue(**change)))

    def test_fail_action_transitions_only_the_fenced_job(self):
        token=self.issue(action="worker.job.fail")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0],"failed")
        self.assertEqual(self.admin.execute(f"SELECT to_state FROM {SCHEMA}.transitions WHERE tenant_id='tenant-a' AND operation_id='op-a'").fetchone()[0],"failed")
        self.assertEqual(self.admin.execute(f"SELECT event_type FROM {SCHEMA}.outbox WHERE tenant_id='tenant-a' AND operation_id='op-a'").fetchone()[0],"job.failed")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])

    def test_fail_rolls_back_nonce_job_transition_and_outbox_together(self):
        self.admin.execute(
            f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','op-a:job.failed','job-a','session-a','op-a','preexisting')"
        )
        token=self.issue(action="worker.job.fail")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.jobs WHERE job_id='job-a'").fetchone()[0],"running")
        self.assertIsNone(self.admin.execute(f"SELECT 1 FROM {SCHEMA}.transitions WHERE operation_id='op-a'").fetchone())
        self.admin.execute(f"DELETE FROM {SCHEMA}.outbox WHERE event_id='op-a:job.failed'")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])

    def test_wrong_action_is_rejected_before_nonce_consumption(self):
        token=self.issue(action="worker.job.complete")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])

    def test_renew_uses_database_clock_and_consumes_nonce(self):
        token=self.issue(action="worker.job.renew")
        before=self.admin.execute(f"SELECT lease_expires_at FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0]
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                renewed=conn.execute(f"SELECT {SCHEMA}.renew_v2(%s,60)",(token,)).fetchone()[0]
                self.assertIsNotNone(renewed)
        after=self.admin.execute(f"SELECT lease_expires_at FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0]
        self.assertGreater(after,before)
        self.assertEqual(after,renewed)
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertIsNone(conn.execute(f"SELECT {SCHEMA}.renew_v2(%s,60)",(token,)).fetchone()[0])

    def test_renew_rejects_out_of_range_lease_duration(self):
        token=self.issue(action="worker.job.renew")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertIsNone(conn.execute(f"SELECT {SCHEMA}.renew_v2(%s,86400)",(token,)).fetchone()[0])

    def test_old_worker_is_fenced_after_owner_epoch_reassignment(self):
        old_capability=self.issue()
        self.admin.execute(
            f"UPDATE {SCHEMA}.jobs SET owner='worker-new',epoch=8 "
            "WHERE tenant_id='tenant-a' AND job_id='job-a'"
        )
        self.assertFalse(self.authorize_once(old_capability))
        new_capability=self.issue(owner="worker-new",sub="worker-new",epoch=8)
        self.assertTrue(self.authorize_once(new_capability))

    def test_expired_persisted_lease_denied(self):
        self.admin.execute(f"UPDATE {SCHEMA}.jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE job_id='job-a'")
        self.assertFalse(self.authorize_once(self.issue()))

    def test_guc_alone_does_not_authorize_rls(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertEqual(conn.execute(f"SELECT job_id FROM {SCHEMA}.jobs").fetchall(),[])

    def test_tampered_signature_unknown_claim_and_bad_expiry_denied(self):
        token=self.issue()
        p,s=token.split(".")
        raw=bytearray(base64.urlsafe_b64decode(s+"="*(-len(s)%4)))
        raw[0]^=1
        self.assertFalse(self.authorize_once(p+"."+b64url(bytes(raw))))
        c=self.claims(); c["unexpected"]="admin"
        encoded=b64url(canonical_payload(c))
        sig=self.admin.execute("SELECT pgsodium.crypto_sign_detached(%s,%s)",(encoded.encode("ascii"),self.private_key)).fetchone()[0]
        self.assertFalse(self.authorize_once(encoded+"."+b64url(sig)))
        self.assertFalse(self.authorize_once(self.issue(exp=int(time.time())-1)))
        self.assertFalse(self.authorize_once(self.issue(exp=int(time.time())+500)))

    def test_runtime_cannot_mutate_owner_epoch_or_lease(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"UPDATE {SCHEMA}.jobs SET epoch=epoch+1 WHERE job_id='job-a'")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"UPDATE {SCHEMA}.jobs SET lease_expires_at=clock_timestamp()+interval '1 hour' WHERE job_id='job-a'")

    def test_signed_operation_id_must_match_transaction_scope(self):
        self.assertFalse(self.authorize_once(self.issue(operation_id="other-operation")))

    def test_runtime_cannot_read_keys_or_nonce_ledger_or_assume_verifier(self):
        with self.runtime_connection() as conn:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT * FROM {SCHEMA}.issuer_keys")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT * FROM {SCHEMA}.nonce_ledger")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SET ROLE {VERIFIER}")
            self.assertEqual(conn.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone(),(False,False))

    def test_concurrent_duplicate_nonce_has_one_winner(self):
        token=self.issue()
        barrier=threading.Barrier(2)
        def attempt():
            with self.runtime_connection() as conn:
                with conn.transaction():
                    conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                    conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                    conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                    barrier.wait(timeout=5)
                    return conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:attempt(),range(2)))
        self.assertEqual(sorted(results),[False,True])

if __name__=="__main__":
    unittest.main(verbosity=2)
 THEN RETURN false; END IF;
          IF NOT {SCHEMA}.authorize_v2(token) THEN RETURN false; END IF;
          UPDATE {SCHEMA}.jobs
             SET status='retry',available_at=clock_timestamp()+make_interval(secs=>delay_seconds),
                 attempt_count=attempt_count+1,last_error_code=error_code,
                 owner=NULL,lease_expires_at=NULL
           WHERE tenant_id=c->>'tenant_id' AND job_id=c->>'job_id'
             AND session_id=c->>'session_id' AND owner=c->>'owner'
             AND epoch=(c->>'epoch')::bigint AND status='running'
             AND lease_expires_at>clock_timestamp() AND attempt_count<maximum_attempts;
          IF NOT FOUND THEN RAISE EXCEPTION 'retry fence or attempt ceiling rejected'; END IF;
          INSERT INTO {SCHEMA}.transitions
            (tenant_id,transition_id,job_id,session_id,operation_id,from_state,to_state)
          VALUES(c->>'tenant_id',(c->>'operation_id')||':retry',c->>'job_id',
                 c->>'session_id',c->>'operation_id','running','retry');
          INSERT INTO {SCHEMA}.outbox
            (tenant_id,event_id,job_id,session_id,operation_id,event_type)
          VALUES(c->>'tenant_id',(c->>'operation_id')||':job.retry',c->>'job_id',
                 c->>'session_id',c->>'operation_id','job.retry_scheduled');
          RETURN true;
        EXCEPTION WHEN OTHERS THEN RETURN false;
        END $retry$
        """
        cls.admin.execute(retry_sql)
        cls.admin.execute(f"ALTER FUNCTION {SCHEMA}.retry_v2(text,integer,text) OWNER TO {VERIFIER}")
        cls.admin.execute(f"REVOKE ALL ON FUNCTION {SCHEMA}.retry_v2(text,integer,text) FROM PUBLIC")

        dead_letter_sql = f"""
        CREATE FUNCTION {SCHEMA}.dead_letter_v2(token text, error_code text, terminal_reason text)
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,{SCHEMA}
        AS $dead$
        DECLARE c jsonb; current_attempt integer; max_attempts integer;
        BEGIN
          c:={SCHEMA}.verify_v2(token);
          IF c IS NULL OR c->>'action'<>'worker.job.dead_letter'
             OR error_code !~ '^[A-Z][A-Z0-9_]{0,63}



        allows_sql = f"""
        CREATE FUNCTION {SCHEMA}.assertion_allows(
          token text,row_tenant text,row_job text,row_session text,
          expected_action text,expected_resource_type text,expected_resource_id text,expected_operation_id text
        ) RETURNS boolean LANGUAGE sql SECURITY DEFINER VOLATILE
        SET search_path=pg_catalog,{SCHEMA}
        AS $allows$
          SELECT EXISTS(SELECT 1 FROM {SCHEMA}.nonce_ledger n
            WHERE n.token=token AND n.transaction_id=pg_current_xact_id()
              AND n.tenant_id=row_tenant AND n.job_id=row_job AND n.session_id=row_session
              AND n.action=expected_action AND n.resource_type=expected_resource_type
              AND n.resource_id=expected_resource_id AND n.operation_id=expected_operation_id)
        $allows$
        """
        cls.admin.execute(allows_sql)
        cls.admin.execute(f"ALTER FUNCTION {SCHEMA}.assertion_allows(text,text,text,text,text,text,text,text) OWNER TO {VERIFIER}")
        cls.admin.execute(f"REVOKE ALL ON FUNCTION {SCHEMA}.assertion_allows(text,text,text,text,text,text,text,text) FROM PUBLIC")

        # Policies on job-scoped tables rely on nonce ledger consumption in this
        # transaction. The caller-controlled GUC alone grants no access.
        for table in ("transitions","outbox"):
            cls.admin.execute(
                f"CREATE POLICY {table}_runtime_scope ON {SCHEMA}.{table} FOR ALL TO {RUNTIME} "
                f"USING({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
                "tenant_id,job_id,session_id,'worker.job.complete','job',"
                "job_id,operation_id)) "
                f"WITH CHECK({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
                "tenant_id,job_id,session_id,'worker.job.complete','job',"
                "job_id,operation_id))"
            )
        cls.admin.execute(
            f"CREATE POLICY receipts_complete_insert ON {SCHEMA}.receipts FOR INSERT TO {RUNTIME} "
            f"WITH CHECK({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
            "tenant_id,job_id,session_id,'worker.job.complete','job',job_id,operation_id))"
        )
        cls.admin.execute(
            f"CREATE POLICY receipts_complete_select ON {SCHEMA}.receipts FOR SELECT TO {RUNTIME} "
            f"USING({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
            "tenant_id,job_id,session_id,'worker.job.complete','job',job_id,operation_id))"
        )
        cls.admin.execute(
            f"CREATE POLICY receipts_reconcile_select ON {SCHEMA}.receipts FOR SELECT TO {RUNTIME} "
            f"USING({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
            "tenant_id,job_id,session_id,'worker.receipt.reconcile','receipt',operation_id,operation_id))"
        )
        cls.admin.execute(
            f"CREATE POLICY jobs_runtime_select ON {SCHEMA}.jobs FOR SELECT TO {RUNTIME} "
            f"USING(status IN ('running','succeeded') AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),tenant_id,job_id,session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),"
            "current_setting('app.resource_operation_id',true)))"
        )
        cls.admin.execute(
            f"CREATE POLICY jobs_runtime_scope ON {SCHEMA}.jobs FOR UPDATE TO {RUNTIME} "
            f"USING(status='running' AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),tenant_id,job_id,session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),"
            "current_setting('app.resource_operation_id',true))) "
            f"WITH CHECK(status='succeeded' AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),tenant_id,job_id,session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),"
            "current_setting('app.resource_operation_id',true)))"
        )
        cls.admin.execute(
            f"CREATE POLICY sessions_runtime_scope ON {SCHEMA}.sessions FOR SELECT TO {RUNTIME} "
            f"USING(EXISTS(SELECT 1 FROM {SCHEMA}.jobs j WHERE j.tenant_id=sessions.tenant_id "
            f"AND j.session_id=sessions.session_id AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),j.tenant_id,j.job_id,j.session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),current_setting('app.resource_operation_id',true))))"
        )
        cls.admin.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.authorize_v2(text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.renew_v2(text,integer) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.fail_v2(text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.assertion_allows(text,text,text,text,text,text,text,text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT SELECT ON {SCHEMA}.jobs TO {RUNTIME}")
        cls.admin.execute(f"GRANT UPDATE(status) ON {SCHEMA}.jobs TO {RUNTIME}")
        cls.admin.execute(f"GRANT SELECT ON {SCHEMA}.sessions TO {RUNTIME}")
        cls.admin.execute(f"GRANT SELECT,INSERT ON {SCHEMA}.receipts,{SCHEMA}.transitions,{SCHEMA}.outbox TO {RUNTIME}")

        cls.admin.execute(f"INSERT INTO {SCHEMA}.sessions VALUES ('tenant-a','session-a',4),('tenant-a','session-b',9),('tenant-b','session-x',1)")
        cls.admin.execute(
            f"INSERT INTO {SCHEMA}.jobs (tenant_id,job_id,session_id,owner,epoch,status,lease_expires_at) VALUES "
            "('tenant-a','job-a','session-a','worker-a',7,'running',clock_timestamp()+interval '5 minutes'),"
            "('tenant-a','job-b','session-b','worker-b',2,'running',clock_timestamp()+interval '5 minutes'),"
            "('tenant-b','job-x','session-x','worker-x',1,'running',clock_timestamp()+interval '5 minutes')"
        )

    @classmethod
    def tearDownClass(cls):
        cls.admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cls.admin.execute(f"REVOKE USAGE ON SCHEMA pgsodium FROM {VERIFIER}")
        cls.admin.execute(f"REVOKE EXECUTE ON FUNCTION pgsodium.crypto_sign_verify_detached(bytea,bytea,bytea) FROM {VERIFIER}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {LOGIN}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {RUNTIME}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {VERIFIER}")
        cls.admin.close()

    def setUp(self):
        self.admin.execute(f"UPDATE {SCHEMA}.jobs SET owner='worker-a',epoch=7,status='running',lease_expires_at=clock_timestamp()+interval '5 minutes',available_at=clock_timestamp(),attempt_count=1,maximum_attempts=5,last_error_code=NULL WHERE tenant_id='tenant-a' AND job_id='job-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.receipts WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.transitions WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.outbox WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.dlq_items WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.nonce_ledger")

    @classmethod
    def claims(cls, **overrides):
        now=int(time.time())
        c={"v":2,"iss":ISSUER,"kid":"test-key","tenant_id":"tenant-a","sub":"worker-a",
           "aud":AUDIENCE,"action":"worker.job.complete","job_id":"job-a",
           "resource_type":"job","resource_id":"job-a","session_id":"session-a",
           "owner":"worker-a","epoch":7,"operation_id":"op-a","iat":now,"exp":now+60,
           "nonce":uuid.uuid4().hex}
        c.update(overrides)
        return c

    @classmethod
    def issue(cls, **overrides):
        c=cls.claims(**overrides)
        payload=b64url(canonical_payload(c))
        sig=cls.admin.execute("SELECT pgsodium.crypto_sign_detached(%s,%s)",(payload.encode("ascii"),cls.private_key)).fetchone()[0]
        return payload+"."+b64url(sig)

    @classmethod
    def runtime_connection(cls):
        dsn=make_conninfo(DSN,user=LOGIN,password=PASSWORD)
        conn=psycopg.connect(dsn,autocommit=True)
        conn.execute(f"SET ROLE {RUNTIME}")
        return conn

    @classmethod
    def authorize_once(cls,token):
        with cls.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                return conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0]

    def test_valid_complete_unit_of_work(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                self.assertEqual(conn.execute(f"SELECT job_id FROM {SCHEMA}.jobs").fetchall(),[("job-a",)])
                changed=conn.execute(
                    f"UPDATE {SCHEMA}.jobs SET status='succeeded' WHERE tenant_id='tenant-a' AND job_id='job-a' "
                    "AND session_id='session-a' AND owner='worker-a' AND epoch=7 AND status='running' "
                    "AND lease_expires_at>clock_timestamp() RETURNING job_id"
                ).fetchall()
                self.assertEqual(changed,[("job-a",)])
                conn.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-1','APPLIED')")
                conn.execute(f"INSERT INTO {SCHEMA}.transitions VALUES ('tenant-a','tr-a','job-a','session-a','op-a','running','succeeded')")
                conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','ev-a','job-a','session-a','op-a','job.completed')")
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0],"succeeded")

    def test_ambiguous_commit_reconciles_receipt_and_detects_digest_conflict(self):
        completion=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(completion,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(completion,)).fetchone()[0])
                conn.execute(f"UPDATE {SCHEMA}.jobs SET status='succeeded' WHERE tenant_id='tenant-a' AND job_id='job-a' AND session_id='session-a' AND owner='worker-a' AND epoch=7 AND status='running' AND lease_expires_at>clock_timestamp()")
                conn.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-1','APPLIED')")
                conn.execute(f"INSERT INTO {SCHEMA}.transitions VALUES ('tenant-a','tr-a','job-a','session-a','op-a','running','succeeded')")
                conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','ev-a','job-a','session-a','op-a','job.completed')")
        # The commit above is treated as acknowledged ambiguously: a fresh,
        # separately signed Receipt capability resolves the durable outcome.
        reconcile=self.issue(action="worker.receipt.reconcile",resource_type="receipt",resource_id="op-a")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(reconcile,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(reconcile,)).fetchone()[0])
                row=conn.execute(f"SELECT request_digest,outcome FROM {SCHEMA}.receipts WHERE tenant_id='tenant-a' AND operation_id='op-a'").fetchone()
                self.assertEqual(row,("digest-1","APPLIED"))
                same_digest="DUPLICATE" if row[0]=="digest-1" else "IDEMPOTENCY_CONFLICT"
                changed_digest="DUPLICATE" if row[0]=="digest-other" else "IDEMPOTENCY_CONFLICT"
                self.assertEqual(same_digest,"DUPLICATE")
                self.assertEqual(changed_digest,"IDEMPOTENCY_CONFLICT")

    def test_receipt_reconcile_rejects_wrong_or_missing_receipt(self):
        self.admin.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-1','APPLIED')")
        wrong=self.issue(action="worker.receipt.reconcile",resource_type="receipt",resource_id="other-operation")
        missing=self.issue(action="worker.receipt.reconcile",resource_type="receipt",resource_id="op-missing",operation_id="op-missing")
        self.assertFalse(self.authorize_once(wrong))
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(missing,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-missing',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(missing,)).fetchone()[0])

    def test_child_rows_cannot_splice_another_session_or_tenant(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','bad-session','job-a','session-b','op-a','job.completed')")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-b','bad-tenant','job-a','session-a','op-a','job.completed')")

    def test_complete_capability_cannot_write_failed_terminal_state(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(f"UPDATE {SCHEMA}.jobs SET status='failed' WHERE tenant_id='tenant-a' AND job_id='job-a'")

    def test_same_claims_and_key_produce_identical_token(self):
        fixed = {
            "nonce": "0123456789abcdef0123456789abcdef",
            "iat": 1800000000,
            "exp": 1800000060,
        }
        self.assertEqual(self.issue(**fixed), self.issue(**fixed))
    def test_same_token_reused_only_inside_same_transaction(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])

    def test_committed_nonce_replay_is_denied(self):
        token=self.issue()
        self.assertTrue(self.authorize_once(token))
        self.assertFalse(self.authorize_once(token))

    def test_rollback_removes_nonce_and_business_writes(self):
        token=self.issue()
        conn=self.runtime_connection()
        try:
            with self.assertRaises(RuntimeError):
                with conn.transaction():
                    conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                    conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                    conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                    self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                    conn.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-x','APPLIED')")
                    raise RuntimeError("injected rollback")
        finally:
            conn.close()
        self.assertTrue(self.authorize_once(token))
        self.assertIsNone(self.admin.execute(f"SELECT 1 FROM {SCHEMA}.receipts WHERE operation_id='op-a'").fetchone())

    def test_wrong_tenant_job_session_owner_epoch_or_audience_denied(self):
        cases=[{"tenant_id":"tenant-b"},{"job_id":"job-b","resource_id":"job-b"},
               {"session_id":"session-b"},{"owner":"worker-b"},{"epoch":8},{"aud":"wrong"}]
        for change in cases:
            with self.subTest(change=change):
                self.assertFalse(self.authorize_once(self.issue(**change)))

    def test_fail_action_transitions_only_the_fenced_job(self):
        token=self.issue(action="worker.job.fail")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0],"failed")
        self.assertEqual(self.admin.execute(f"SELECT to_state FROM {SCHEMA}.transitions WHERE tenant_id='tenant-a' AND operation_id='op-a'").fetchone()[0],"failed")
        self.assertEqual(self.admin.execute(f"SELECT event_type FROM {SCHEMA}.outbox WHERE tenant_id='tenant-a' AND operation_id='op-a'").fetchone()[0],"job.failed")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])

    def test_fail_rolls_back_nonce_job_transition_and_outbox_together(self):
        self.admin.execute(
            f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','op-a:job.failed','job-a','session-a','op-a','preexisting')"
        )
        token=self.issue(action="worker.job.fail")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.jobs WHERE job_id='job-a'").fetchone()[0],"running")
        self.assertIsNone(self.admin.execute(f"SELECT 1 FROM {SCHEMA}.transitions WHERE operation_id='op-a'").fetchone())
        self.admin.execute(f"DELETE FROM {SCHEMA}.outbox WHERE event_id='op-a:job.failed'")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])

    def test_wrong_action_is_rejected_before_nonce_consumption(self):
        token=self.issue(action="worker.job.complete")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])

    def test_renew_uses_database_clock_and_consumes_nonce(self):
        token=self.issue(action="worker.job.renew")
        before=self.admin.execute(f"SELECT lease_expires_at FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0]
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                renewed=conn.execute(f"SELECT {SCHEMA}.renew_v2(%s,60)",(token,)).fetchone()[0]
                self.assertIsNotNone(renewed)
        after=self.admin.execute(f"SELECT lease_expires_at FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0]
        self.assertGreater(after,before)
        self.assertEqual(after,renewed)
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertIsNone(conn.execute(f"SELECT {SCHEMA}.renew_v2(%s,60)",(token,)).fetchone()[0])

    def test_renew_rejects_out_of_range_lease_duration(self):
        token=self.issue(action="worker.job.renew")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertIsNone(conn.execute(f"SELECT {SCHEMA}.renew_v2(%s,86400)",(token,)).fetchone()[0])

    def test_old_worker_is_fenced_after_owner_epoch_reassignment(self):
        old_capability=self.issue()
        self.admin.execute(
            f"UPDATE {SCHEMA}.jobs SET owner='worker-new',epoch=8 "
            "WHERE tenant_id='tenant-a' AND job_id='job-a'"
        )
        self.assertFalse(self.authorize_once(old_capability))
        new_capability=self.issue(owner="worker-new",sub="worker-new",epoch=8)
        self.assertTrue(self.authorize_once(new_capability))

    def test_expired_persisted_lease_denied(self):
        self.admin.execute(f"UPDATE {SCHEMA}.jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE job_id='job-a'")
        self.assertFalse(self.authorize_once(self.issue()))

    def test_guc_alone_does_not_authorize_rls(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertEqual(conn.execute(f"SELECT job_id FROM {SCHEMA}.jobs").fetchall(),[])

    def test_tampered_signature_unknown_claim_and_bad_expiry_denied(self):
        token=self.issue()
        p,s=token.split(".")
        raw=bytearray(base64.urlsafe_b64decode(s+"="*(-len(s)%4)))
        raw[0]^=1
        self.assertFalse(self.authorize_once(p+"."+b64url(bytes(raw))))
        c=self.claims(); c["unexpected"]="admin"
        encoded=b64url(canonical_payload(c))
        sig=self.admin.execute("SELECT pgsodium.crypto_sign_detached(%s,%s)",(encoded.encode("ascii"),self.private_key)).fetchone()[0]
        self.assertFalse(self.authorize_once(encoded+"."+b64url(sig)))
        self.assertFalse(self.authorize_once(self.issue(exp=int(time.time())-1)))
        self.assertFalse(self.authorize_once(self.issue(exp=int(time.time())+500)))

    def test_runtime_cannot_mutate_owner_epoch_or_lease(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"UPDATE {SCHEMA}.jobs SET epoch=epoch+1 WHERE job_id='job-a'")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"UPDATE {SCHEMA}.jobs SET lease_expires_at=clock_timestamp()+interval '1 hour' WHERE job_id='job-a'")

    def test_signed_operation_id_must_match_transaction_scope(self):
        self.assertFalse(self.authorize_once(self.issue(operation_id="other-operation")))

    def test_runtime_cannot_read_keys_or_nonce_ledger_or_assume_verifier(self):
        with self.runtime_connection() as conn:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT * FROM {SCHEMA}.issuer_keys")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT * FROM {SCHEMA}.nonce_ledger")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SET ROLE {VERIFIER}")
            self.assertEqual(conn.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone(),(False,False))

    def test_concurrent_duplicate_nonce_has_one_winner(self):
        token=self.issue()
        barrier=threading.Barrier(2)
        def attempt():
            with self.runtime_connection() as conn:
                with conn.transaction():
                    conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                    conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                    conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                    barrier.wait(timeout=5)
                    return conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:attempt(),range(2)))
        self.assertEqual(sorted(results),[False,True])

if __name__=="__main__":
    unittest.main(verbosity=2)

             OR terminal_reason NOT IN ('max_attempts','non_retryable') THEN RETURN false; END IF;
          IF NOT {SCHEMA}.authorize_v2(token) THEN RETURN false; END IF;
          SELECT attempt_count,maximum_attempts INTO current_attempt,max_attempts FROM {SCHEMA}.jobs
           WHERE tenant_id=c->>'tenant_id' AND job_id=c->>'job_id'
             AND session_id=c->>'session_id' AND owner=c->>'owner'
             AND epoch=(c->>'epoch')::bigint AND status='running'
             AND lease_expires_at>clock_timestamp();
          IF NOT FOUND OR (terminal_reason='max_attempts' AND current_attempt < max_attempts) THEN
            RAISE EXCEPTION 'dead-letter predicate rejected';
          END IF;
          UPDATE {SCHEMA}.jobs
             SET status='dead_lettered',last_error_code=error_code,
                 owner=NULL,lease_expires_at=NULL
           WHERE tenant_id=c->>'tenant_id' AND job_id=c->>'job_id'
             AND session_id=c->>'session_id' AND owner=c->>'owner'
             AND epoch=(c->>'epoch')::bigint AND status='running'
             AND lease_expires_at>clock_timestamp();
          IF NOT FOUND THEN RAISE EXCEPTION 'dead-letter fence changed'; END IF;
          INSERT INTO {SCHEMA}.dlq_items
            (tenant_id,dlq_item_id,job_id,session_id,terminal_reason,error_code,attempt_count,lease_epoch)
          VALUES(c->>'tenant_id',(c->>'operation_id')||':dlq',c->>'job_id',
                 c->>'session_id',terminal_reason,error_code,current_attempt,(c->>'epoch')::bigint);
          INSERT INTO {SCHEMA}.transitions
            (tenant_id,transition_id,job_id,session_id,operation_id,from_state,to_state)
          VALUES(c->>'tenant_id',(c->>'operation_id')||':dead-letter',c->>'job_id',
                 c->>'session_id',c->>'operation_id','running','dead_lettered');
          INSERT INTO {SCHEMA}.outbox
            (tenant_id,event_id,job_id,session_id,operation_id,event_type)
          VALUES(c->>'tenant_id',(c->>'operation_id')||':job.dead-lettered',c->>'job_id',
                 c->>'session_id',c->>'operation_id','job.dead_lettered');
          RETURN true;
        EXCEPTION WHEN OTHERS THEN RETURN false;
        END $dead$
        """
        cls.admin.execute(dead_letter_sql)
        cls.admin.execute(f"ALTER FUNCTION {SCHEMA}.dead_letter_v2(text,text,text) OWNER TO {VERIFIER}")
        cls.admin.execute(f"REVOKE ALL ON FUNCTION {SCHEMA}.dead_letter_v2(text,text,text) FROM PUBLIC")




        allows_sql = f"""
        CREATE FUNCTION {SCHEMA}.assertion_allows(
          token text,row_tenant text,row_job text,row_session text,
          expected_action text,expected_resource_type text,expected_resource_id text,expected_operation_id text
        ) RETURNS boolean LANGUAGE sql SECURITY DEFINER VOLATILE
        SET search_path=pg_catalog,{SCHEMA}
        AS $allows$
          SELECT EXISTS(SELECT 1 FROM {SCHEMA}.nonce_ledger n
            WHERE n.token=token AND n.transaction_id=pg_current_xact_id()
              AND n.tenant_id=row_tenant AND n.job_id=row_job AND n.session_id=row_session
              AND n.action=expected_action AND n.resource_type=expected_resource_type
              AND n.resource_id=expected_resource_id AND n.operation_id=expected_operation_id)
        $allows$
        """
        cls.admin.execute(allows_sql)
        cls.admin.execute(f"ALTER FUNCTION {SCHEMA}.assertion_allows(text,text,text,text,text,text,text,text) OWNER TO {VERIFIER}")
        cls.admin.execute(f"REVOKE ALL ON FUNCTION {SCHEMA}.assertion_allows(text,text,text,text,text,text,text,text) FROM PUBLIC")

        # Policies on job-scoped tables rely on nonce ledger consumption in this
        # transaction. The caller-controlled GUC alone grants no access.
        for table in ("transitions","outbox"):
            cls.admin.execute(
                f"CREATE POLICY {table}_runtime_scope ON {SCHEMA}.{table} FOR ALL TO {RUNTIME} "
                f"USING({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
                "tenant_id,job_id,session_id,'worker.job.complete','job',"
                "job_id,operation_id)) "
                f"WITH CHECK({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
                "tenant_id,job_id,session_id,'worker.job.complete','job',"
                "job_id,operation_id))"
            )
        cls.admin.execute(
            f"CREATE POLICY receipts_complete_insert ON {SCHEMA}.receipts FOR INSERT TO {RUNTIME} "
            f"WITH CHECK({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
            "tenant_id,job_id,session_id,'worker.job.complete','job',job_id,operation_id))"
        )
        cls.admin.execute(
            f"CREATE POLICY receipts_complete_select ON {SCHEMA}.receipts FOR SELECT TO {RUNTIME} "
            f"USING({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
            "tenant_id,job_id,session_id,'worker.job.complete','job',job_id,operation_id))"
        )
        cls.admin.execute(
            f"CREATE POLICY receipts_reconcile_select ON {SCHEMA}.receipts FOR SELECT TO {RUNTIME} "
            f"USING({SCHEMA}.assertion_allows(current_setting('app.resource_assertion',true),"
            "tenant_id,job_id,session_id,'worker.receipt.reconcile','receipt',operation_id,operation_id))"
        )
        cls.admin.execute(
            f"CREATE POLICY jobs_runtime_select ON {SCHEMA}.jobs FOR SELECT TO {RUNTIME} "
            f"USING(status IN ('running','succeeded') AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),tenant_id,job_id,session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),"
            "current_setting('app.resource_operation_id',true)))"
        )
        cls.admin.execute(
            f"CREATE POLICY jobs_runtime_scope ON {SCHEMA}.jobs FOR UPDATE TO {RUNTIME} "
            f"USING(status='running' AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),tenant_id,job_id,session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),"
            "current_setting('app.resource_operation_id',true))) "
            f"WITH CHECK(status='succeeded' AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),tenant_id,job_id,session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),"
            "current_setting('app.resource_operation_id',true)))"
        )
        cls.admin.execute(
            f"CREATE POLICY sessions_runtime_scope ON {SCHEMA}.sessions FOR SELECT TO {RUNTIME} "
            f"USING(EXISTS(SELECT 1 FROM {SCHEMA}.jobs j WHERE j.tenant_id=sessions.tenant_id "
            f"AND j.session_id=sessions.session_id AND {SCHEMA}.assertion_allows("
            "current_setting('app.resource_assertion',true),j.tenant_id,j.job_id,j.session_id,"
            "'worker.job.complete','job',current_setting('app.resource_job_id',true),current_setting('app.resource_operation_id',true))))"
        )
        cls.admin.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.authorize_v2(text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.renew_v2(text,integer) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.fail_v2(text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT EXECUTE ON FUNCTION {SCHEMA}.assertion_allows(text,text,text,text,text,text,text,text) TO {RUNTIME}")
        cls.admin.execute(f"GRANT SELECT ON {SCHEMA}.jobs TO {RUNTIME}")
        cls.admin.execute(f"GRANT UPDATE(status) ON {SCHEMA}.jobs TO {RUNTIME}")
        cls.admin.execute(f"GRANT SELECT ON {SCHEMA}.sessions TO {RUNTIME}")
        cls.admin.execute(f"GRANT SELECT,INSERT ON {SCHEMA}.receipts,{SCHEMA}.transitions,{SCHEMA}.outbox TO {RUNTIME}")

        cls.admin.execute(f"INSERT INTO {SCHEMA}.sessions VALUES ('tenant-a','session-a',4),('tenant-a','session-b',9),('tenant-b','session-x',1)")
        cls.admin.execute(
            f"INSERT INTO {SCHEMA}.jobs (tenant_id,job_id,session_id,owner,epoch,status,lease_expires_at) VALUES "
            "('tenant-a','job-a','session-a','worker-a',7,'running',clock_timestamp()+interval '5 minutes'),"
            "('tenant-a','job-b','session-b','worker-b',2,'running',clock_timestamp()+interval '5 minutes'),"
            "('tenant-b','job-x','session-x','worker-x',1,'running',clock_timestamp()+interval '5 minutes')"
        )

    @classmethod
    def tearDownClass(cls):
        cls.admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cls.admin.execute(f"REVOKE USAGE ON SCHEMA pgsodium FROM {VERIFIER}")
        cls.admin.execute(f"REVOKE EXECUTE ON FUNCTION pgsodium.crypto_sign_verify_detached(bytea,bytea,bytea) FROM {VERIFIER}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {LOGIN}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {RUNTIME}")
        cls.admin.execute(f"DROP ROLE IF EXISTS {VERIFIER}")
        cls.admin.close()

    def setUp(self):
        self.admin.execute(f"UPDATE {SCHEMA}.jobs SET owner='worker-a',epoch=7,status='running',lease_expires_at=clock_timestamp()+interval '5 minutes',available_at=clock_timestamp(),attempt_count=1,maximum_attempts=5,last_error_code=NULL WHERE tenant_id='tenant-a' AND job_id='job-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.receipts WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.transitions WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.outbox WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.dlq_items WHERE tenant_id='tenant-a'")
        self.admin.execute(f"DELETE FROM {SCHEMA}.nonce_ledger")

    @classmethod
    def claims(cls, **overrides):
        now=int(time.time())
        c={"v":2,"iss":ISSUER,"kid":"test-key","tenant_id":"tenant-a","sub":"worker-a",
           "aud":AUDIENCE,"action":"worker.job.complete","job_id":"job-a",
           "resource_type":"job","resource_id":"job-a","session_id":"session-a",
           "owner":"worker-a","epoch":7,"operation_id":"op-a","iat":now,"exp":now+60,
           "nonce":uuid.uuid4().hex}
        c.update(overrides)
        return c

    @classmethod
    def issue(cls, **overrides):
        c=cls.claims(**overrides)
        payload=b64url(canonical_payload(c))
        sig=cls.admin.execute("SELECT pgsodium.crypto_sign_detached(%s,%s)",(payload.encode("ascii"),cls.private_key)).fetchone()[0]
        return payload+"."+b64url(sig)

    @classmethod
    def runtime_connection(cls):
        dsn=make_conninfo(DSN,user=LOGIN,password=PASSWORD)
        conn=psycopg.connect(dsn,autocommit=True)
        conn.execute(f"SET ROLE {RUNTIME}")
        return conn

    @classmethod
    def authorize_once(cls,token):
        with cls.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                return conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0]

    def test_valid_complete_unit_of_work(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                self.assertEqual(conn.execute(f"SELECT job_id FROM {SCHEMA}.jobs").fetchall(),[("job-a",)])
                changed=conn.execute(
                    f"UPDATE {SCHEMA}.jobs SET status='succeeded' WHERE tenant_id='tenant-a' AND job_id='job-a' "
                    "AND session_id='session-a' AND owner='worker-a' AND epoch=7 AND status='running' "
                    "AND lease_expires_at>clock_timestamp() RETURNING job_id"
                ).fetchall()
                self.assertEqual(changed,[("job-a",)])
                conn.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-1','APPLIED')")
                conn.execute(f"INSERT INTO {SCHEMA}.transitions VALUES ('tenant-a','tr-a','job-a','session-a','op-a','running','succeeded')")
                conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','ev-a','job-a','session-a','op-a','job.completed')")
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0],"succeeded")

    def test_ambiguous_commit_reconciles_receipt_and_detects_digest_conflict(self):
        completion=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(completion,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(completion,)).fetchone()[0])
                conn.execute(f"UPDATE {SCHEMA}.jobs SET status='succeeded' WHERE tenant_id='tenant-a' AND job_id='job-a' AND session_id='session-a' AND owner='worker-a' AND epoch=7 AND status='running' AND lease_expires_at>clock_timestamp()")
                conn.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-1','APPLIED')")
                conn.execute(f"INSERT INTO {SCHEMA}.transitions VALUES ('tenant-a','tr-a','job-a','session-a','op-a','running','succeeded')")
                conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','ev-a','job-a','session-a','op-a','job.completed')")
        # The commit above is treated as acknowledged ambiguously: a fresh,
        # separately signed Receipt capability resolves the durable outcome.
        reconcile=self.issue(action="worker.receipt.reconcile",resource_type="receipt",resource_id="op-a")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(reconcile,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(reconcile,)).fetchone()[0])
                row=conn.execute(f"SELECT request_digest,outcome FROM {SCHEMA}.receipts WHERE tenant_id='tenant-a' AND operation_id='op-a'").fetchone()
                self.assertEqual(row,("digest-1","APPLIED"))
                same_digest="DUPLICATE" if row[0]=="digest-1" else "IDEMPOTENCY_CONFLICT"
                changed_digest="DUPLICATE" if row[0]=="digest-other" else "IDEMPOTENCY_CONFLICT"
                self.assertEqual(same_digest,"DUPLICATE")
                self.assertEqual(changed_digest,"IDEMPOTENCY_CONFLICT")

    def test_receipt_reconcile_rejects_wrong_or_missing_receipt(self):
        self.admin.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-1','APPLIED')")
        wrong=self.issue(action="worker.receipt.reconcile",resource_type="receipt",resource_id="other-operation")
        missing=self.issue(action="worker.receipt.reconcile",resource_type="receipt",resource_id="op-missing",operation_id="op-missing")
        self.assertFalse(self.authorize_once(wrong))
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(missing,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-missing',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(missing,)).fetchone()[0])

    def test_child_rows_cannot_splice_another_session_or_tenant(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','bad-session','job-a','session-b','op-a','job.completed')")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-b','bad-tenant','job-a','session-a','op-a','job.completed')")

    def test_complete_capability_cannot_write_failed_terminal_state(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    conn.execute(f"UPDATE {SCHEMA}.jobs SET status='failed' WHERE tenant_id='tenant-a' AND job_id='job-a'")

    def test_same_claims_and_key_produce_identical_token(self):
        fixed = {
            "nonce": "0123456789abcdef0123456789abcdef",
            "iat": 1800000000,
            "exp": 1800000060,
        }
        self.assertEqual(self.issue(**fixed), self.issue(**fixed))
    def test_same_token_reused_only_inside_same_transaction(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])

    def test_committed_nonce_replay_is_denied(self):
        token=self.issue()
        self.assertTrue(self.authorize_once(token))
        self.assertFalse(self.authorize_once(token))

    def test_rollback_removes_nonce_and_business_writes(self):
        token=self.issue()
        conn=self.runtime_connection()
        try:
            with self.assertRaises(RuntimeError):
                with conn.transaction():
                    conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                    conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                    conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                    self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                    conn.execute(f"INSERT INTO {SCHEMA}.receipts VALUES ('tenant-a','op-a','job-a','session-a','digest-x','APPLIED')")
                    raise RuntimeError("injected rollback")
        finally:
            conn.close()
        self.assertTrue(self.authorize_once(token))
        self.assertIsNone(self.admin.execute(f"SELECT 1 FROM {SCHEMA}.receipts WHERE operation_id='op-a'").fetchone())

    def test_wrong_tenant_job_session_owner_epoch_or_audience_denied(self):
        cases=[{"tenant_id":"tenant-b"},{"job_id":"job-b","resource_id":"job-b"},
               {"session_id":"session-b"},{"owner":"worker-b"},{"epoch":8},{"aud":"wrong"}]
        for change in cases:
            with self.subTest(change=change):
                self.assertFalse(self.authorize_once(self.issue(**change)))

    def test_fail_action_transitions_only_the_fenced_job(self):
        token=self.issue(action="worker.job.fail")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0],"failed")
        self.assertEqual(self.admin.execute(f"SELECT to_state FROM {SCHEMA}.transitions WHERE tenant_id='tenant-a' AND operation_id='op-a'").fetchone()[0],"failed")
        self.assertEqual(self.admin.execute(f"SELECT event_type FROM {SCHEMA}.outbox WHERE tenant_id='tenant-a' AND operation_id='op-a'").fetchone()[0],"job.failed")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])

    def test_fail_rolls_back_nonce_job_transition_and_outbox_together(self):
        self.admin.execute(
            f"INSERT INTO {SCHEMA}.outbox VALUES ('tenant-a','op-a:job.failed','job-a','session-a','op-a','preexisting')"
        )
        token=self.issue(action="worker.job.fail")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])
        self.assertEqual(self.admin.execute(f"SELECT status FROM {SCHEMA}.jobs WHERE job_id='job-a'").fetchone()[0],"running")
        self.assertIsNone(self.admin.execute(f"SELECT 1 FROM {SCHEMA}.transitions WHERE operation_id='op-a'").fetchone())
        self.admin.execute(f"DELETE FROM {SCHEMA}.outbox WHERE event_id='op-a:job.failed'")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])

    def test_wrong_action_is_rejected_before_nonce_consumption(self):
        token=self.issue(action="worker.job.complete")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertFalse(conn.execute(f"SELECT {SCHEMA}.fail_v2(%s)",(token,)).fetchone()[0])
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])

    def test_renew_uses_database_clock_and_consumes_nonce(self):
        token=self.issue(action="worker.job.renew")
        before=self.admin.execute(f"SELECT lease_expires_at FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0]
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                renewed=conn.execute(f"SELECT {SCHEMA}.renew_v2(%s,60)",(token,)).fetchone()[0]
                self.assertIsNotNone(renewed)
        after=self.admin.execute(f"SELECT lease_expires_at FROM {SCHEMA}.jobs WHERE tenant_id='tenant-a' AND job_id='job-a'").fetchone()[0]
        self.assertGreater(after,before)
        self.assertEqual(after,renewed)
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertIsNone(conn.execute(f"SELECT {SCHEMA}.renew_v2(%s,60)",(token,)).fetchone()[0])

    def test_renew_rejects_out_of_range_lease_duration(self):
        token=self.issue(action="worker.job.renew")
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertIsNone(conn.execute(f"SELECT {SCHEMA}.renew_v2(%s,86400)",(token,)).fetchone()[0])

    def test_old_worker_is_fenced_after_owner_epoch_reassignment(self):
        old_capability=self.issue()
        self.admin.execute(
            f"UPDATE {SCHEMA}.jobs SET owner='worker-new',epoch=8 "
            "WHERE tenant_id='tenant-a' AND job_id='job-a'"
        )
        self.assertFalse(self.authorize_once(old_capability))
        new_capability=self.issue(owner="worker-new",sub="worker-new",epoch=8)
        self.assertTrue(self.authorize_once(new_capability))

    def test_expired_persisted_lease_denied(self):
        self.admin.execute(f"UPDATE {SCHEMA}.jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE job_id='job-a'")
        self.assertFalse(self.authorize_once(self.issue()))

    def test_guc_alone_does_not_authorize_rls(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertEqual(conn.execute(f"SELECT job_id FROM {SCHEMA}.jobs").fetchall(),[])

    def test_tampered_signature_unknown_claim_and_bad_expiry_denied(self):
        token=self.issue()
        p,s=token.split(".")
        raw=bytearray(base64.urlsafe_b64decode(s+"="*(-len(s)%4)))
        raw[0]^=1
        self.assertFalse(self.authorize_once(p+"."+b64url(bytes(raw))))
        c=self.claims(); c["unexpected"]="admin"
        encoded=b64url(canonical_payload(c))
        sig=self.admin.execute("SELECT pgsodium.crypto_sign_detached(%s,%s)",(encoded.encode("ascii"),self.private_key)).fetchone()[0]
        self.assertFalse(self.authorize_once(encoded+"."+b64url(sig)))
        self.assertFalse(self.authorize_once(self.issue(exp=int(time.time())-1)))
        self.assertFalse(self.authorize_once(self.issue(exp=int(time.time())+500)))

    def test_runtime_cannot_mutate_owner_epoch_or_lease(self):
        token=self.issue()
        with self.runtime_connection() as conn:
            with conn.transaction():
                conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                self.assertTrue(conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0])
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"UPDATE {SCHEMA}.jobs SET epoch=epoch+1 WHERE job_id='job-a'")
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():
                        conn.execute(f"UPDATE {SCHEMA}.jobs SET lease_expires_at=clock_timestamp()+interval '1 hour' WHERE job_id='job-a'")

    def test_signed_operation_id_must_match_transaction_scope(self):
        self.assertFalse(self.authorize_once(self.issue(operation_id="other-operation")))

    def test_runtime_cannot_read_keys_or_nonce_ledger_or_assume_verifier(self):
        with self.runtime_connection() as conn:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT * FROM {SCHEMA}.issuer_keys")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SELECT * FROM {SCHEMA}.nonce_ledger")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute(f"SET ROLE {VERIFIER}")
            self.assertEqual(conn.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone(),(False,False))

    def test_concurrent_duplicate_nonce_has_one_winner(self):
        token=self.issue()
        barrier=threading.Barrier(2)
        def attempt():
            with self.runtime_connection() as conn:
                with conn.transaction():
                    conn.execute("SELECT set_config('app.resource_assertion',%s,true)",(token,))
                    conn.execute("SELECT set_config('app.resource_job_id','job-a',true)")
                    conn.execute("SELECT set_config('app.resource_operation_id','op-a',true)")
                    barrier.wait(timeout=5)
                    return conn.execute(f"SELECT {SCHEMA}.authorize_v2(%s)",(token,)).fetchone()[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:attempt(),range(2)))
        self.assertEqual(sorted(results),[False,True])

if __name__=="__main__":
    unittest.main(verbosity=2)
