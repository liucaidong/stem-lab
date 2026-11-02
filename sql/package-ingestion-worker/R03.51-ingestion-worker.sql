-- R03.51 reference DDL. Requires the R03.50 session/transition/receipt/outbox tables.
-- Replace stemlab_ingest with the deployment schema. This is not a production migration.
CREATE TABLE stemlab_ingest.ingestion_jobs (
 tenant_id text NOT NULL, job_id text NOT NULL, session_id text NOT NULL,
 package_id text NOT NULL, package_version text NOT NULL, job_type text NOT NULL,
 status text NOT NULL CHECK(status IN ('queued','running','retry','succeeded','dead_lettered','cancelled')),
 priority integer NOT NULL DEFAULT 0, payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
 maximum_attempts integer NOT NULL DEFAULT 5 CHECK(maximum_attempts BETWEEN 1 AND 100),
 available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 lease_owner text, lease_expires_at timestamptz,
 lease_epoch bigint NOT NULL DEFAULT 0 CHECK(lease_epoch >= 0),
 last_error_code text, last_error_safe_message text, completed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,job_id),
 FOREIGN KEY(tenant_id,session_id) REFERENCES stemlab_ingest.sessions(tenant_id,session_id),
 CHECK((status='running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (status<>'running' AND lease_owner IS NULL AND lease_expires_at IS NULL)),
 CHECK((status='succeeded') = (completed_at IS NOT NULL))
);
CREATE UNIQUE INDEX ingestion_jobs_one_active_type
 ON stemlab_ingest.ingestion_jobs(tenant_id,session_id,job_type)
 WHERE status IN ('queued','running','retry');
CREATE INDEX ingestion_jobs_claim_queue
 ON stemlab_ingest.ingestion_jobs(priority DESC,available_at,created_at,job_id)
 WHERE status IN ('queued','retry');
CREATE INDEX ingestion_jobs_expired_lease
 ON stemlab_ingest.ingestion_jobs(lease_expires_at,priority DESC,created_at,job_id)
 WHERE status='running';
CREATE TABLE stemlab_ingest.ingestion_job_dlq(
 tenant_id text NOT NULL, job_id text NOT NULL,
 dead_lettered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 terminal_reason text NOT NULL CHECK(terminal_reason IN ('max_attempts','non_retryable')),
 error_code text NOT NULL, safe_message text NOT NULL,
 attempt_count integer NOT NULL CHECK(attempt_count>0),
 lease_epoch bigint NOT NULL CHECK(lease_epoch>0),
 replay_count integer NOT NULL DEFAULT 0 CHECK(replay_count>=0),
 PRIMARY KEY(tenant_id,job_id),
 FOREIGN KEY(tenant_id,job_id) REFERENCES stemlab_ingest.ingestion_jobs(tenant_id,job_id)
);
CREATE INDEX ingestion_job_dlq_recent
 ON stemlab_ingest.ingestion_job_dlq(tenant_id,dead_lettered_at DESC);
-- Separate from the R03.50 session-sequenced outbox: job events do not advance Session revision.
CREATE TABLE stemlab_ingest.ingestion_job_outbox(
 tenant_id text NOT NULL, event_id text NOT NULL, job_id text NOT NULL,
 lease_epoch bigint NOT NULL, event_type text NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), published_at timestamptz,
 PRIMARY KEY(tenant_id,event_id),
 UNIQUE(tenant_id,job_id,lease_epoch,event_type),
 FOREIGN KEY(tenant_id,job_id) REFERENCES stemlab_ingest.ingestion_jobs(tenant_id,job_id)
);
ALTER TABLE stemlab_ingest.ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE stemlab_ingest.ingestion_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY ingestion_jobs_tenant_isolation ON stemlab_ingest.ingestion_jobs
 USING(tenant_id=current_setting('app.tenant_id',true))
 WITH CHECK(tenant_id=current_setting('app.tenant_id',true));
ALTER TABLE stemlab_ingest.ingestion_job_dlq ENABLE ROW LEVEL SECURITY;
ALTER TABLE stemlab_ingest.ingestion_job_dlq FORCE ROW LEVEL SECURITY;
CREATE POLICY ingestion_job_dlq_tenant_isolation ON stemlab_ingest.ingestion_job_dlq
 USING(tenant_id=current_setting('app.tenant_id',true))
 WITH CHECK(tenant_id=current_setting('app.tenant_id',true));
ALTER TABLE stemlab_ingest.ingestion_job_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE stemlab_ingest.ingestion_job_outbox FORCE ROW LEVEL SECURITY;
CREATE POLICY ingestion_job_outbox_tenant_isolation ON stemlab_ingest.ingestion_job_outbox
 USING(tenant_id=current_setting('app.tenant_id',true))
 WITH CHECK(tenant_id=current_setting('app.tenant_id',true));
