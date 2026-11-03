-- Disposable conformance implementation for v2alpha2 Receipt arbitration.
-- Replace __SCHEMA__ with a unique schema before executing this file.
CREATE SCHEMA IF NOT EXISTS __SCHEMA__;

CREATE TABLE __SCHEMA__.request_receipts_v2alpha2 (
  receipt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id text NOT NULL,
  action text NOT NULL,
  idempotency_key text NOT NULL,
  operation_id text NOT NULL,
  request_digest text NOT NULL,
  resource_type text NOT NULL,
  resource_id text NOT NULL,
  receipt_status text NOT NULL DEFAULT 'pending'
    CHECK (receipt_status IN ('pending', 'succeeded', 'failed')),
  outcome jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT request_receipts_v2alpha2_idempotency_uq
    UNIQUE (tenant_id, action, idempotency_key),
  CONSTRAINT request_receipts_v2alpha2_operation_uq
    UNIQUE (tenant_id, operation_id),
  CONSTRAINT request_receipts_v2alpha2_digest_ck
    CHECK (request_digest ~ '^sha256:[0-9a-f]{64}$')
);

ALTER TABLE __SCHEMA__.request_receipts_v2alpha2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE __SCHEMA__.request_receipts_v2alpha2 FORCE ROW LEVEL SECURITY;
CREATE POLICY request_receipts_v2alpha2_tenant_isolation
  ON __SCHEMA__.request_receipts_v2alpha2
  USING (tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE OR REPLACE FUNCTION __SCHEMA__.reserve_request_receipt_v2alpha2(
  p_tenant_id text,
  p_action text,
  p_idempotency_key text,
  p_operation_id text,
  p_request_digest text,
  p_resource_type text,
  p_resource_id text
)
RETURNS TABLE (
  receipt_id bigint,
  created boolean,
  receipt_status text,
  stored_digest text,
  stored_operation_id text,
  outcome jsonb
)
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog
AS $fn$
DECLARE
  v_receipt_id bigint;
  v_digest text;
  v_operation_id text;
  v_resource_type text;
  v_resource_id text;
BEGIN
  IF p_tenant_id IS NULL OR p_tenant_id = '' OR length(p_tenant_id) > 256
     OR p_action IS NULL OR p_action = '' OR length(p_action) > 128
     OR p_idempotency_key IS NULL OR p_idempotency_key = '' OR length(p_idempotency_key) > 256
     OR p_operation_id IS NULL OR p_operation_id = '' OR length(p_operation_id) > 256
     OR p_resource_type IS NULL OR p_resource_type = '' OR length(p_resource_type) > 128
     OR p_resource_id IS NULL OR p_resource_id = '' OR length(p_resource_id) > 256
     OR p_request_digest IS NULL
     OR p_request_digest !~ '^sha256:[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'INVALID_RECEIPT_IDENTITY';
  END IF;

  INSERT INTO __SCHEMA__.request_receipts_v2alpha2 AS r (
    tenant_id, action, idempotency_key, operation_id, request_digest,
    resource_type, resource_id
  )
  VALUES (
    p_tenant_id, p_action, p_idempotency_key, p_operation_id, p_request_digest,
    p_resource_type, p_resource_id
  )
  ON CONFLICT (tenant_id, action, idempotency_key) DO NOTHING
  RETURNING r.receipt_id INTO v_receipt_id;

  IF v_receipt_id IS NOT NULL THEN
    RETURN QUERY
      SELECT r.receipt_id, true, r.receipt_status, r.request_digest,
             r.operation_id, r.outcome
        FROM __SCHEMA__.request_receipts_v2alpha2 AS r
       WHERE r.receipt_id = v_receipt_id;
    RETURN;
  END IF;

  SELECT r.receipt_id, r.request_digest, r.operation_id, r.resource_type, r.resource_id
    INTO v_receipt_id, v_digest, v_operation_id, v_resource_type, v_resource_id
    FROM __SCHEMA__.request_receipts_v2alpha2 AS r
   WHERE r.tenant_id = p_tenant_id
     AND r.action = p_action
     AND r.idempotency_key = p_idempotency_key
   FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = '40001', MESSAGE = 'RECEIPT_ARBITRATION_RETRY';
  END IF;
  IF v_digest <> p_request_digest
     OR v_operation_id <> p_operation_id
     OR v_resource_type <> p_resource_type
     OR v_resource_id <> p_resource_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'IDEMPOTENCY_CONFLICT';
  END IF;

  RETURN QUERY
    SELECT r.receipt_id, false, r.receipt_status, r.request_digest,
           r.operation_id, r.outcome
      FROM __SCHEMA__.request_receipts_v2alpha2 AS r
     WHERE r.receipt_id = v_receipt_id;
EXCEPTION
  WHEN unique_violation THEN
    -- A concurrent identical first-use request may hit the operation_id unique
    -- index before ON CONFLICT handles the idempotency-key index. Re-arbitrate
    -- by the complete idempotency identity before declaring an operation clash.
    SELECT r.receipt_id, r.request_digest, r.operation_id, r.resource_type, r.resource_id
      INTO v_receipt_id, v_digest, v_operation_id, v_resource_type, v_resource_id
      FROM __SCHEMA__.request_receipts_v2alpha2 AS r
     WHERE r.tenant_id = p_tenant_id
       AND r.action = p_action
       AND r.idempotency_key = p_idempotency_key
     FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'OPERATION_ID_CONFLICT';
    END IF;
    IF v_digest <> p_request_digest
       OR v_operation_id <> p_operation_id
       OR v_resource_type <> p_resource_type
       OR v_resource_id <> p_resource_id THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'IDEMPOTENCY_CONFLICT';
    END IF;
    RETURN QUERY
      SELECT r.receipt_id, false, r.receipt_status, r.request_digest,
             r.operation_id, r.outcome
        FROM __SCHEMA__.request_receipts_v2alpha2 AS r
       WHERE r.receipt_id = v_receipt_id;
END;
$fn$;


CREATE OR REPLACE FUNCTION __SCHEMA__.lookup_request_receipt_v2alpha2(
  p_tenant_id text, p_action text, p_idempotency_key text, p_operation_id text,
  p_request_digest text, p_resource_type text, p_resource_id text
)
RETURNS TABLE (receipt_id bigint, created boolean, receipt_status text,
               stored_digest text, stored_operation_id text, outcome jsonb)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
AS $fn$
DECLARE
  v_row __SCHEMA__.request_receipts_v2alpha2%ROWTYPE;
BEGIN
  IF p_tenant_id IS NULL OR p_tenant_id = '' OR length(p_tenant_id) > 256
     OR p_action IS NULL OR p_action = '' OR length(p_action) > 128
     OR p_idempotency_key IS NULL OR p_idempotency_key = '' OR length(p_idempotency_key) > 256
     OR p_operation_id IS NULL OR p_operation_id = '' OR length(p_operation_id) > 256
     OR p_resource_type IS NULL OR p_resource_type = '' OR length(p_resource_type) > 128
     OR p_resource_id IS NULL OR p_resource_id = '' OR length(p_resource_id) > 256
     OR p_request_digest IS NULL
     OR p_request_digest !~ '^sha256:[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'INVALID_RECEIPT_LOOKUP';
  END IF;
  SELECT r.* INTO v_row
    FROM __SCHEMA__.request_receipts_v2alpha2 AS r
   WHERE r.tenant_id = p_tenant_id
     AND r.action = p_action
     AND r.idempotency_key = p_idempotency_key;
  IF NOT FOUND THEN RETURN; END IF;
  IF v_row.request_digest <> p_request_digest
     OR v_row.operation_id <> p_operation_id
     OR v_row.resource_type <> p_resource_type
     OR v_row.resource_id <> p_resource_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'IDEMPOTENCY_CONFLICT';
  END IF;
  RETURN QUERY SELECT v_row.receipt_id, false, v_row.receipt_status,
                      v_row.request_digest, v_row.operation_id, v_row.outcome;
END;
$fn$;

CREATE OR REPLACE FUNCTION __SCHEMA__.finalize_request_receipt_v2alpha2(
  p_receipt_id bigint,
  p_tenant_id text,
  p_action text,
  p_idempotency_key text,
  p_request_digest text,
  p_final_status text,
  p_outcome jsonb
)
RETURNS TABLE (
  receipt_id bigint,
  receipt_status text,
  outcome jsonb
)
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog
AS $fn$
DECLARE
  v_status text;
  v_outcome jsonb;
BEGIN
  IF p_receipt_id IS NULL
     OR p_tenant_id IS NULL OR p_tenant_id = '' OR length(p_tenant_id) > 256
     OR p_action IS NULL OR p_action = '' OR length(p_action) > 128
     OR p_idempotency_key IS NULL OR p_idempotency_key = '' OR length(p_idempotency_key) > 256
     OR p_request_digest IS NULL OR p_request_digest !~ '^sha256:[0-9a-f]{64}$'
     OR p_final_status IS NULL
     OR p_final_status NOT IN ('succeeded', 'failed')
     OR p_outcome IS NULL
     OR pg_catalog.jsonb_typeof(p_outcome) IS DISTINCT FROM 'object'
     OR pg_catalog.octet_length(pg_catalog.convert_to(p_outcome::text, 'UTF8')) > 16384 THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'INVALID_RECEIPT_FINALIZATION';
  END IF;

  UPDATE __SCHEMA__.request_receipts_v2alpha2 AS r
     SET receipt_status = p_final_status,
         outcome = p_outcome,
         updated_at = clock_timestamp()
   WHERE r.receipt_id = p_receipt_id
     AND r.tenant_id = p_tenant_id
     AND r.action = p_action
     AND r.idempotency_key = p_idempotency_key
     AND r.request_digest = p_request_digest
     AND r.receipt_status = 'pending'
  RETURNING r.receipt_id, r.receipt_status, r.outcome
       INTO receipt_id, receipt_status, outcome;

  IF FOUND THEN
    RETURN NEXT;
    RETURN;
  END IF;

  SELECT r.receipt_status, r.outcome
    INTO v_status, v_outcome
    FROM __SCHEMA__.request_receipts_v2alpha2 AS r
   WHERE r.receipt_id = p_receipt_id
     AND r.tenant_id = p_tenant_id
     AND r.action = p_action
     AND r.idempotency_key = p_idempotency_key
     AND r.request_digest = p_request_digest
   FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'RECEIPT_NOT_FOUND';
  END IF;
  IF v_status <> p_final_status OR v_outcome IS DISTINCT FROM p_outcome THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'RECEIPT_ALREADY_FINALIZED';
  END IF;

  RETURN QUERY
    SELECT p_receipt_id, v_status, v_outcome;
END;
$fn$;


REVOKE ALL ON TABLE __SCHEMA__.request_receipts_v2alpha2 FROM PUBLIC;
-- Runtime roles must receive explicit grants through a reviewed deployment migration.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA __SCHEMA__ FROM PUBLIC;
