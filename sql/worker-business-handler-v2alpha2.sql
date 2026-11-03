-- Atomic v2alpha2 package-validation completion and read-only Receipt reconciliation.
-- Requires Request Digest, Receipt, Nonce Ledger and R03.51 session/job/transition/outbox DDL.
-- Replace __SCHEMA__ with the deployment schema. Own these SECURITY DEFINER functions
-- with a dedicated NOLOGIN NOSUPERUSER NOBYPASSRLS role; grant runtime EXECUTE only.
CREATE OR REPLACE FUNCTION __SCHEMA__.apply_job_complete_v2alpha2(
  p_payload_b64url text, p_signature_b64url text, p_operation_arguments jsonb
)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
DECLARE
  v_claim jsonb; v_tenant text; v_job_id text; v_session_id text;
  v_operation_id text; v_idempotency_key text; v_digest text; v_nonce text;
  v_receipt_id bigint; v_receipt_created boolean; v_receipt_status text;
  v_existing_outcome jsonb; v_job __SCHEMA__.ingestion_jobs%ROWTYPE;
  v_session __SCHEMA__.sessions%ROWTYPE; v_expected_revision numeric;
  v_resulting_revision integer; v_result_ref text; v_outcome jsonb;
BEGIN
  v_claim := __SCHEMA__.verify_request_assertion_v2alpha2(
    p_payload_b64url,p_signature_b64url,p_operation_arguments);
  IF v_claim->>'aud' <> 'stemlab-worker-store'
     OR v_claim->>'action' <> 'worker.job.complete'
     OR v_claim->>'resource_type' <> 'job'
     OR v_claim->>'resource_id' <> v_claim->>'job_id'
     OR v_claim->>'sub' <> v_claim->>'owner' THEN
    RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='ASSERTION_SCOPE_MISMATCH';
  END IF;
  IF pg_catalog.jsonb_typeof(p_operation_arguments) IS DISTINCT FROM 'object'
     OR pg_catalog.jsonb_typeof(p_operation_arguments->'expected_session_revision') IS DISTINCT FROM 'number'
     OR pg_catalog.jsonb_typeof(p_operation_arguments->'result_ref') IS DISTINCT FROM 'string'
     OR length(p_operation_arguments->>'result_ref') NOT BETWEEN 1 AND 256 THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='INVALID_JOB_COMPLETE_ARGUMENTS';
  END IF;
  v_expected_revision := (p_operation_arguments->>'expected_session_revision')::numeric;
  IF v_expected_revision < 0 OR v_expected_revision > 2147483646
     OR v_expected_revision <> trunc(v_expected_revision) THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='INVALID_EXPECTED_SESSION_REVISION';
  END IF;
  v_tenant:=v_claim->>'tenant_id'; v_job_id:=v_claim->>'job_id';
  v_session_id:=v_claim->>'session_id'; v_operation_id:=v_claim->>'operation_id';
  v_idempotency_key:=v_claim->>'idempotency_key'; v_digest:=v_claim->>'request_digest';
  v_nonce:=v_claim->>'nonce'; v_result_ref:=p_operation_arguments->>'result_ref';
  PERFORM pg_catalog.set_config('app.tenant_id',v_tenant,true);
  BEGIN
    INSERT INTO __SCHEMA__.request_nonce_ledger_v2alpha2
      (tenant_id,issuer,kid,nonce,operation_id,request_digest,action,resource_type,resource_id,assertion_expires_at)
    VALUES (v_tenant,v_claim->>'iss',v_claim->>'kid',v_nonce,v_operation_id,
      v_digest,v_claim->>'action',v_claim->>'resource_type',v_claim->>'resource_id',
      to_timestamp((v_claim->>'exp')::bigint));
  EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='NONCE_REPLAY';
  END;
  SELECT r.receipt_id,r.created,r.receipt_status,r.outcome
    INTO v_receipt_id,v_receipt_created,v_receipt_status,v_existing_outcome
    FROM __SCHEMA__.reserve_request_receipt_v2alpha2(
      v_tenant,v_claim->>'action',v_idempotency_key,v_operation_id,v_digest,
      v_claim->>'resource_type',v_claim->>'resource_id') AS r;
  IF NOT v_receipt_created THEN
    IF v_receipt_status='pending' THEN
      RETURN pg_catalog.jsonb_build_object('status','pending','receipt_id',v_receipt_id,'operation_id',v_operation_id);
    END IF;
    RETURN pg_catalog.jsonb_build_object('status','duplicate','receipt_status',v_receipt_status,
      'receipt_id',v_receipt_id,'outcome',v_existing_outcome);
  END IF;
  -- Global lock order: Nonce -> Receipt -> Job -> Session.
  SELECT j.* INTO v_job FROM __SCHEMA__.ingestion_jobs AS j
   WHERE j.tenant_id=v_tenant AND j.job_id=v_job_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0002',MESSAGE='JOB_NOT_FOUND'; END IF;
  IF v_job.job_type<>'package.validate' OR v_job.session_id<>v_session_id
     OR v_job.status<>'running' OR v_job.lease_owner<>(v_claim->>'owner')
     OR v_job.lease_epoch<>(v_claim->>'epoch')::bigint
     OR v_job.lease_expires_at IS NULL OR v_job.lease_expires_at<=clock_timestamp() THEN
    RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='STALE_OR_INVALID_JOB_LEASE';
  END IF;
  SELECT s.* INTO v_session FROM __SCHEMA__.sessions AS s
   WHERE s.tenant_id=v_tenant AND s.session_id=v_session_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='P0002',MESSAGE='SESSION_NOT_FOUND'; END IF;
  IF v_session.revision<>v_expected_revision OR v_session.status<>'quarantined' THEN
    RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='SESSION_REVISION_OR_STATE_CONFLICT';
  END IF;
  v_resulting_revision:=v_session.revision+1;
  UPDATE __SCHEMA__.sessions SET status='validated',revision=v_resulting_revision,updated_at=clock_timestamp()
   WHERE tenant_id=v_tenant AND session_id=v_session_id;
  UPDATE __SCHEMA__.ingestion_jobs SET status='succeeded',lease_owner=NULL,lease_expires_at=NULL,
      completed_at=clock_timestamp(),updated_at=clock_timestamp()
   WHERE tenant_id=v_tenant AND job_id=v_job_id;
  INSERT INTO __SCHEMA__.transitions
    (tenant_id,session_id,sequence,from_state,to_state,command_id,idempotency_key,
     request_digest,actor_id,expected_revision,resulting_revision)
  VALUES (v_tenant,v_session_id,v_resulting_revision,v_session.status,'validated',v_operation_id,
    v_idempotency_key,v_digest,v_claim->>'sub',v_session.revision,v_resulting_revision);
  INSERT INTO __SCHEMA__.outbox(tenant_id,event_id,session_id,sequence,event_type,payload)
  VALUES (v_tenant,v_operation_id,v_session_id,v_resulting_revision,'session.validated',
    pg_catalog.jsonb_build_object('tenant_id',v_tenant,'job_id',v_job_id,'session_id',v_session_id,
      'session_revision',v_resulting_revision,'result_ref',v_result_ref,
      'operation_id',v_operation_id,'request_digest',v_digest));
  v_outcome:=pg_catalog.jsonb_build_object('status','succeeded','job_id',v_job_id,
    'session_id',v_session_id,'session_revision',v_resulting_revision,'result_ref',v_result_ref);
  PERFORM 1 FROM __SCHEMA__.finalize_request_receipt_v2alpha2(
    v_receipt_id,v_tenant,v_claim->>'action',v_idempotency_key,v_digest,'succeeded',v_outcome);
  RETURN pg_catalog.jsonb_build_object('status','applied','receipt_id',v_receipt_id,'outcome',v_outcome);
END;
$fn$;

CREATE OR REPLACE FUNCTION __SCHEMA__.reconcile_request_receipt_v2alpha2(
  p_payload_b64url text,p_signature_b64url text,p_operation_arguments jsonb
)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $fn$
DECLARE v_claim jsonb; v_row __SCHEMA__.request_receipts_v2alpha2%ROWTYPE;
BEGIN
  v_claim:=__SCHEMA__.verify_request_assertion_v2alpha2(
    p_payload_b64url,p_signature_b64url,p_operation_arguments);
  IF v_claim->>'aud'<>'stemlab-worker-store'
     OR v_claim->>'action'<>'worker.receipt.reconcile'
     OR v_claim->>'resource_type'<>'receipt'
     OR v_claim->>'resource_id'<>v_claim->>'operation_id'
     OR v_claim->>'sub'<>v_claim->>'owner' THEN
    RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='ASSERTION_SCOPE_MISMATCH';
  END IF;
  PERFORM pg_catalog.set_config('app.tenant_id',v_claim->>'tenant_id',true);
  BEGIN
    INSERT INTO __SCHEMA__.request_nonce_ledger_v2alpha2
      (tenant_id,issuer,kid,nonce,operation_id,request_digest,action,resource_type,resource_id,assertion_expires_at)
    VALUES (v_claim->>'tenant_id',v_claim->>'iss',v_claim->>'kid',v_claim->>'nonce',
      v_claim->>'operation_id',v_claim->>'request_digest',v_claim->>'action',
      v_claim->>'resource_type',v_claim->>'resource_id',
      to_timestamp((v_claim->>'exp')::bigint));
  EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='NONCE_REPLAY';
  END;
  SELECT r.* INTO v_row FROM __SCHEMA__.request_receipts_v2alpha2 AS r
   WHERE r.tenant_id=v_claim->>'tenant_id' AND r.operation_id=v_claim->>'operation_id';
  IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('status','missing'); END IF;
  IF v_row.idempotency_key<>v_claim->>'idempotency_key' THEN
    RETURN pg_catalog.jsonb_build_object('status','inconsistent');
  END IF;
  IF v_row.receipt_status='pending' THEN
    RETURN pg_catalog.jsonb_build_object('status','pending','receipt_id',v_row.receipt_id,'action',v_row.action);
  END IF;
  RETURN pg_catalog.jsonb_build_object('status','terminal','receipt_id',v_row.receipt_id,
    'receipt_status',v_row.receipt_status,'action',v_row.action,
    'request_digest',v_row.request_digest,'outcome',v_row.outcome);
END;
$fn$;
REVOKE ALL ON FUNCTION __SCHEMA__.apply_job_complete_v2alpha2(text,text,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION __SCHEMA__.reconcile_request_receipt_v2alpha2(text,text,jsonb) FROM PUBLIC;
