-- Disposable conformance helper for Request Digest v2alpha2.
-- Replace __SCHEMA__ with a unique schema before executing this file.
CREATE SCHEMA IF NOT EXISTS __SCHEMA__;

-- Parse the original JSON text before jsonb conversion so duplicate members remain observable.
CREATE OR REPLACE FUNCTION __SCHEMA__.json_has_duplicate_keys_v2alpha2(p_value json, p_depth integer DEFAULT 0)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $fn$
DECLARE
  child record;
  duplicate_found boolean;
BEGIN
  IF p_depth > 32 THEN RAISE EXCEPTION 'request claim nesting depth exceeded'; END IF;
  IF pg_catalog.json_typeof(p_value) = 'object' THEN
    SELECT EXISTS (
      SELECT 1 FROM (
        SELECT key FROM pg_catalog.json_each(p_value)
        GROUP BY key HAVING pg_catalog.count(*) > 1
      ) duplicates
    ) INTO duplicate_found;
    IF duplicate_found THEN RETURN true; END IF;
    FOR child IN SELECT value FROM pg_catalog.json_each(p_value) LOOP
      IF __SCHEMA__.json_has_duplicate_keys_v2alpha2(child.value, p_depth + 1) THEN RETURN true; END IF;
    END LOOP;
  ELSIF pg_catalog.json_typeof(p_value) = 'array' THEN
    FOR child IN SELECT value FROM pg_catalog.json_array_elements(p_value) LOOP
      IF __SCHEMA__.json_has_duplicate_keys_v2alpha2(child.value, p_depth + 1) THEN RETURN true; END IF;
    END LOOP;
  END IF;
  RETURN false;
END;
$fn$;

CREATE OR REPLACE FUNCTION __SCHEMA__.parse_strict_json_object_v2alpha2(p_raw text)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $fn$
DECLARE
  parsed json;
BEGIN
  IF pg_catalog.octet_length(pg_catalog.convert_to(p_raw, 'UTF8')) > 16384 THEN
    RAISE EXCEPTION 'request claim payload too large';
  END IF;
  parsed := p_raw::json;
  IF pg_catalog.json_typeof(parsed) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'request claim must be a JSON object';
  END IF;
  IF __SCHEMA__.json_has_duplicate_keys_v2alpha2(parsed, 0) THEN
    RAISE EXCEPTION 'duplicate JSON object key in request claim';
  END IF;
  RETURN parsed::jsonb;
END;
$fn$;

CREATE OR REPLACE FUNCTION __SCHEMA__.encode_typed_value_v2alpha2(p_value jsonb, p_depth integer DEFAULT 0)
RETURNS bytea
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $fn$
DECLARE
  kind text;
  raw bytea;
  result bytea;
  item record;
  item_count integer;
  n numeric;
BEGIN
  IF p_depth > 32 THEN RAISE EXCEPTION 'request digest nesting depth exceeded'; END IF;
  kind := pg_catalog.jsonb_typeof(p_value);

  IF kind = 'null' THEN RETURN decode('4e','hex'); END IF;
  IF kind = 'boolean' THEN
    IF p_value = 'true'::jsonb THEN RETURN decode('54','hex'); END IF;
    RETURN decode('46','hex');
  END IF;
  IF kind = 'number' THEN
    n := (p_value::text)::numeric;
    IF pg_catalog.scale(n) <> 0 OR n < -9223372036854775808 OR n > 9223372036854775807 THEN
      RAISE EXCEPTION 'request digest integer must be signed int64';
    END IF;
    raw := pg_catalog.convert_to(pg_catalog.trunc(n)::text, 'UTF8');
    IF pg_catalog.octet_length(raw) > 2147483647 THEN RAISE EXCEPTION 'integer encoding too long'; END IF;
    RETURN decode('49','hex') || pg_catalog.int4send(pg_catalog.octet_length(raw)) || raw;
  END IF;
  IF kind = 'string' THEN
    raw := pg_catalog.convert_to(p_value #>> '{}', 'UTF8');
    IF pg_catalog.octet_length(raw) > 2147483647 THEN RAISE EXCEPTION 'string encoding too long'; END IF;
    RETURN decode('53','hex') || pg_catalog.int4send(pg_catalog.octet_length(raw)) || raw;
  END IF;
  IF kind = 'array' THEN
    item_count := pg_catalog.jsonb_array_length(p_value);
    IF item_count > 4096 THEN RAISE EXCEPTION 'request digest array too large'; END IF;
    result := decode('41','hex') || pg_catalog.int4send(item_count);
    FOR item IN
      SELECT value FROM pg_catalog.jsonb_array_elements(p_value) WITH ORDINALITY AS a(value, ord)
      ORDER BY ord
    LOOP
      result := result || __SCHEMA__.encode_typed_value_v2alpha2(item.value, p_depth + 1);
    END LOOP;
    RETURN result;
  END IF;
  IF kind = 'object' THEN
    SELECT pg_catalog.count(*)::integer INTO item_count FROM pg_catalog.jsonb_object_keys(p_value);
    IF item_count > 4096 THEN RAISE EXCEPTION 'request digest object too large'; END IF;
    result := decode('4f','hex') || pg_catalog.int4send(item_count);
    FOR item IN
      SELECT key, value FROM pg_catalog.jsonb_each(p_value)
      ORDER BY pg_catalog.convert_to(key, 'UTF8')
    LOOP
      raw := pg_catalog.convert_to(item.key, 'UTF8');
      IF pg_catalog.octet_length(raw) > 2147483647 THEN RAISE EXCEPTION 'object key too long'; END IF;
      result := result || pg_catalog.int4send(pg_catalog.octet_length(raw)) || raw
                       || __SCHEMA__.encode_typed_value_v2alpha2(item.value, p_depth + 1);
    END LOOP;
    RETURN result;
  END IF;
  RAISE EXCEPTION 'unsupported JSON value type for request digest';
END;
$fn$;

CREATE OR REPLACE FUNCTION __SCHEMA__.request_digest_v2alpha2(p_envelope jsonb)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $fn$
DECLARE
  required_fields text[] := ARRAY[
    'contract_version','action','tenant_id','job_id','session_id','resource_type',
    'resource_id','operation_id','idempotency_key','operation_arguments'
  ];
  field_name text;
  field_value text;
  action_name text;
  resource_name text;
  expected_resource text;
  args jsonb;
  expected_args text[];
  raw bytea;
  canonical bytea;
  encoded_args bytea;
BEGIN
  IF pg_catalog.jsonb_typeof(p_envelope) IS DISTINCT FROM 'object'
     OR NOT (p_envelope ?& required_fields)
     OR (p_envelope - required_fields) <> '{}'::jsonb THEN
    RAISE EXCEPTION 'request envelope fields missing or unknown';
  END IF;

  action_name := p_envelope->>'action';
  resource_name := p_envelope->>'resource_type';
  IF p_envelope->>'contract_version' <> '2alpha2' THEN RAISE EXCEPTION 'unsupported request contract version'; END IF;

  expected_args := CASE action_name
    WHEN 'worker.job.renew' THEN ARRAY['lease_seconds']
    WHEN 'worker.job.complete' THEN ARRAY['expected_session_revision','result_ref']
    WHEN 'worker.job.fail' THEN ARRAY['error_code','retryable','retry_delay_micros','safe_message']
    WHEN 'worker.job.retry' THEN ARRAY['delay_seconds','error_code']
    WHEN 'worker.job.dead_letter' THEN ARRAY['error_code','terminal_reason']
    WHEN 'worker.dlq.replay' THEN ARRAY[]::text[]
    WHEN 'worker.outbox.dispatch' THEN ARRAY['lease_seconds']
    WHEN 'worker.receipt.reconcile' THEN ARRAY[]::text[]
    WHEN 'worker.outbox.ack' THEN ARRAY[]::text[]
    ELSE NULL
  END;
  IF expected_args IS NULL THEN RAISE EXCEPTION 'unsupported request action'; END IF;

  expected_resource := CASE
    WHEN action_name LIKE 'worker.job.%' THEN 'job'
    WHEN action_name = 'worker.dlq.replay' THEN 'dlq_item'
    WHEN action_name IN ('worker.outbox.dispatch','worker.outbox.ack') THEN 'outbox_event'
    WHEN action_name = 'worker.receipt.reconcile' THEN 'receipt'
    ELSE NULL
  END;
  IF resource_name IS DISTINCT FROM expected_resource THEN
    RAISE EXCEPTION 'action/resource type mismatch';
  END IF;
  IF action_name LIKE 'worker.job.%' AND p_envelope->>'resource_id' <> p_envelope->>'job_id' THEN
    RAISE EXCEPTION 'Job resource id mismatch';
  END IF;
  IF action_name = 'worker.receipt.reconcile' AND p_envelope->>'resource_id' <> p_envelope->>'operation_id' THEN
    RAISE EXCEPTION 'Receipt resource id mismatch';
  END IF;

  FOREACH field_name IN ARRAY required_fields[1:9] LOOP
    IF pg_catalog.jsonb_typeof(p_envelope->field_name) IS DISTINCT FROM 'string' THEN
      RAISE EXCEPTION 'request envelope identity field must be string: %', field_name;
    END IF;
    field_value := p_envelope->>field_name;
    IF field_value = '' OR pg_catalog.length(field_value) > 256
       OR field_value ~ '[[:cntrl:]]' THEN
      RAISE EXCEPTION 'invalid request envelope identity field: %', field_name;
    END IF;
  END LOOP;

  args := p_envelope->'operation_arguments';
  IF pg_catalog.jsonb_typeof(args) IS DISTINCT FROM 'object'
     OR (SELECT pg_catalog.count(*) FROM pg_catalog.jsonb_object_keys(args)) <> pg_catalog.cardinality(expected_args)
     OR (pg_catalog.cardinality(expected_args) > 0 AND NOT (args ?& expected_args)) THEN
    RAISE EXCEPTION 'operation arguments missing or unknown for action %', action_name;
  END IF;

  IF action_name IN ('worker.job.renew','worker.outbox.dispatch') THEN
    IF pg_catalog.jsonb_typeof(args->'lease_seconds') <> 'number'
       OR pg_catalog.scale((args->>'lease_seconds')::numeric) <> 0
       OR (args->>'lease_seconds')::numeric NOT BETWEEN 5 AND 3600 THEN RAISE EXCEPTION 'invalid lease_seconds'; END IF;
  ELSIF action_name = 'worker.job.complete' THEN
    IF pg_catalog.jsonb_typeof(args->'expected_session_revision') <> 'number'
       OR pg_catalog.scale((args->>'expected_session_revision')::numeric) <> 0
       OR (args->>'expected_session_revision')::numeric < 0
       OR pg_catalog.jsonb_typeof(args->'result_ref') <> 'string'
       OR args->>'result_ref' = '' THEN RAISE EXCEPTION 'invalid complete arguments'; END IF;
  ELSIF action_name = 'worker.job.fail' THEN
    IF pg_catalog.jsonb_typeof(args->'error_code') <> 'string'
       OR args->>'error_code' !~ '^[A-Z][A-Z0-9_]{0,63}$'
       OR pg_catalog.jsonb_typeof(args->'retryable') <> 'boolean'
       OR pg_catalog.jsonb_typeof(args->'retry_delay_micros') <> 'number'
       OR pg_catalog.scale((args->>'retry_delay_micros')::numeric) <> 0
       OR (args->>'retry_delay_micros')::numeric < 0
       OR pg_catalog.jsonb_typeof(args->'safe_message') <> 'string' THEN RAISE EXCEPTION 'invalid fail arguments'; END IF;
  ELSIF action_name = 'worker.job.retry' THEN
    IF pg_catalog.jsonb_typeof(args->'delay_seconds') <> 'number'
       OR pg_catalog.scale((args->>'delay_seconds')::numeric) <> 0
       OR (args->>'delay_seconds')::numeric NOT BETWEEN 1 AND 86400
       OR pg_catalog.jsonb_typeof(args->'error_code') <> 'string'
       OR args->>'error_code' !~ '^[A-Z][A-Z0-9_]{0,63}$' THEN RAISE EXCEPTION 'invalid retry arguments'; END IF;
  ELSIF action_name = 'worker.job.dead_letter' THEN
    IF pg_catalog.jsonb_typeof(args->'error_code') <> 'string'
       OR args->>'error_code' !~ '^[A-Z][A-Z0-9_]{0,63}$'
       OR pg_catalog.jsonb_typeof(args->'terminal_reason') <> 'string'
       OR args->>'terminal_reason' NOT IN ('max_attempts','non_retryable') THEN RAISE EXCEPTION 'invalid dead-letter arguments'; END IF;
  END IF;

  canonical := decode('5354454d4c41422d524551554553542d444947455354007632616c7068613200','hex');
  FOREACH field_name IN ARRAY required_fields[1:9] LOOP
    field_value := p_envelope->>field_name;
    raw := pg_catalog.convert_to(field_value,'UTF8');
    IF pg_catalog.octet_length(raw) > 2147483647 THEN RAISE EXCEPTION 'request field too long'; END IF;
    canonical := canonical || decode('53','hex') || pg_catalog.int4send(pg_catalog.octet_length(raw)) || raw;
  END LOOP;
  encoded_args := __SCHEMA__.encode_typed_value_v2alpha2(args,0);
  canonical := canonical || decode('4a','hex') || pg_catalog.int4send(pg_catalog.octet_length(encoded_args)) || encoded_args;
  RETURN 'sha256:' || pg_catalog.encode(pg_catalog.sha256(canonical),'hex');
END;
$fn$;

CREATE OR REPLACE FUNCTION __SCHEMA__.assert_request_digest_v2alpha2(p_claim jsonb, p_operation_arguments jsonb)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $fn$
DECLARE
  envelope jsonb;
  calculated text;
BEGIN
  IF pg_catalog.jsonb_typeof(p_claim) IS DISTINCT FROM 'object'
     OR p_claim->>'contract_version' <> '2alpha2'
     OR pg_catalog.jsonb_typeof(p_claim->'request_digest') IS DISTINCT FROM 'string'
     OR p_claim->>'request_digest' !~ '^sha256:[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid v2alpha2 digest claim';
  END IF;
  envelope := pg_catalog.jsonb_build_object(
    'contract_version',p_claim->'contract_version',
    'action',p_claim->'action',
    'tenant_id',p_claim->'tenant_id',
    'job_id',p_claim->'job_id',
    'session_id',p_claim->'session_id',
    'resource_type',p_claim->'resource_type',
    'resource_id',p_claim->'resource_id',
    'operation_id',p_claim->'operation_id',
    'idempotency_key',p_claim->'idempotency_key',
    'operation_arguments',p_operation_arguments
  );
  calculated := __SCHEMA__.request_digest_v2alpha2(envelope);
  RETURN calculated = p_claim->>'request_digest';
END;
$fn$;

CREATE OR REPLACE FUNCTION __SCHEMA__.verify_request_assertion_v2alpha2(
  p_payload_b64url text,
  p_signature_b64url text,
  p_operation_arguments jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
AS $fn$
DECLARE
  payload_bytes bytea;
  signature_bytes bytea;
  raw_payload text;
  claim jsonb;
  public_key bytea;
  now_s bigint;
  claim_field text;
  allowed_fields text[] := ARRAY[
    'contract_version','action','tenant_id','job_id','session_id','resource_type',
    'resource_id','operation_id','idempotency_key','request_digest',
    'v','iss','kid','sub','aud','owner','epoch','iat','exp','nonce'
  ];
BEGIN
  IF p_payload_b64url IS NULL OR p_signature_b64url IS NULL
     OR length(p_payload_b64url) NOT BETWEEN 1 AND 21846
     OR p_payload_b64url !~ '^[A-Za-z0-9_-]+$'
     OR p_signature_b64url !~ '^[A-Za-z0-9_-]+$' THEN
    RAISE EXCEPTION 'invalid v2alpha2 compact assertion encoding';
  END IF;
  payload_bytes := decode(rpad(translate(p_payload_b64url, '-_', '+/'),
    ((length(p_payload_b64url) + 3) / 4) * 4, '='), 'base64');
  signature_bytes := decode(rpad(translate(p_signature_b64url, '-_', '+/'),
    ((length(p_signature_b64url) + 3) / 4) * 4, '='), 'base64');
  IF octet_length(payload_bytes) > 16384 OR octet_length(signature_bytes) <> 64 THEN
    RAISE EXCEPTION 'v2alpha2 assertion size or signature length invalid';
  END IF;
  raw_payload := convert_from(payload_bytes, 'UTF8');
  claim := __SCHEMA__.parse_strict_json_object_v2alpha2(raw_payload);
  IF NOT (claim ?& allowed_fields) OR (claim - allowed_fields) <> '{}'::jsonb THEN
    RAISE EXCEPTION 'v2alpha2 assertion fields missing or unknown';
  END IF;
  IF claim->>'contract_version' <> '2alpha2'
     OR jsonb_typeof(claim->'v') IS DISTINCT FROM 'number' OR claim->>'v' <> '2'
     OR jsonb_typeof(claim->'epoch') IS DISTINCT FROM 'number'
     OR jsonb_typeof(claim->'iat') IS DISTINCT FROM 'number'
     OR jsonb_typeof(claim->'exp') IS DISTINCT FROM 'number' THEN
    RAISE EXCEPTION 'v2alpha2 assertion version or numeric claim invalid';
  END IF;
  FOREACH claim_field IN ARRAY ARRAY[
    'iss','kid','action','tenant_id','job_id','session_id','resource_type',
    'resource_id','operation_id','idempotency_key','request_digest','sub','aud','owner','nonce'
  ] LOOP
    IF jsonb_typeof(claim->claim_field) IS DISTINCT FROM 'string'
       OR claim->>claim_field = '' THEN
      RAISE EXCEPTION 'v2alpha2 assertion string claim invalid: %', claim_field;
    END IF;
  END LOOP;
  IF (claim->>'epoch')::numeric <> trunc((claim->>'epoch')::numeric)
     OR (claim->>'iat')::numeric <> trunc((claim->>'iat')::numeric)
     OR (claim->>'exp')::numeric <> trunc((claim->>'exp')::numeric)
     OR (claim->>'epoch')::numeric < 1 OR (claim->>'iat')::numeric < 0
     OR (claim->>'exp')::numeric < 1 THEN
    RAISE EXCEPTION 'v2alpha2 assertion integer claim invalid';
  END IF;
  IF length(claim->>'nonce') NOT BETWEEN 16 AND 256
     OR claim->>'nonce' !~ '^[A-Za-z0-9_-]+$'
     OR claim->>'request_digest' !~ '^sha256:[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'v2alpha2 assertion nonce or digest invalid';
  END IF;
  now_s := floor(extract(epoch FROM clock_timestamp()))::bigint;
  IF (claim->>'iat')::bigint > now_s OR (claim->>'exp')::bigint <= now_s
     OR (claim->>'exp')::bigint <= (claim->>'iat')::bigint
     OR (claim->>'exp')::bigint - (claim->>'iat')::bigint > 120 THEN
    RAISE EXCEPTION 'v2alpha2 assertion time window invalid';
  END IF;
  SELECT k.public_key INTO public_key FROM __SCHEMA__.issuer_keys AS k
   WHERE k.kid = claim->>'kid' AND k.issuer = claim->>'iss'
     AND k.revoked_at IS NULL AND k.not_before <= clock_timestamp()
     AND (k.not_after IS NULL OR k.not_after > clock_timestamp());
  IF NOT FOUND OR public_key IS NULL THEN RAISE EXCEPTION 'v2alpha2 issuer key unavailable'; END IF;
  IF NOT pgsodium.crypto_sign_verify_detached(signature_bytes, payload_bytes, public_key) THEN
    RAISE EXCEPTION 'v2alpha2 assertion signature invalid';
  END IF;
  IF NOT __SCHEMA__.assert_request_digest_v2alpha2(claim, p_operation_arguments) THEN
    RAISE EXCEPTION 'v2alpha2 request digest mismatch';
  END IF;
  RETURN claim;
END;
$fn$;
