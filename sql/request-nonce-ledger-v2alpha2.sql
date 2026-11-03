-- v2alpha2 nonce ledger. Writes are made only by SECURITY DEFINER handler/reconcile entry points.
-- Replace __SCHEMA__ with the deployment schema before execution.
CREATE TABLE __SCHEMA__.request_nonce_ledger_v2alpha2 (
  tenant_id text NOT NULL CHECK (length(tenant_id) BETWEEN 1 AND 256),
  issuer text NOT NULL CHECK (length(issuer) BETWEEN 1 AND 256),
  kid text NOT NULL CHECK (length(kid) BETWEEN 1 AND 128),
  nonce text NOT NULL CHECK (length(nonce) BETWEEN 16 AND 256 AND nonce ~ '^[A-Za-z0-9_-]+$'),
  operation_id text NOT NULL CHECK (length(operation_id) BETWEEN 1 AND 256),
  request_digest text NOT NULL CHECK (request_digest ~ '^sha256:[0-9a-f]{64}$'),
  action text NOT NULL CHECK (length(action) BETWEEN 1 AND 128),
  resource_type text NOT NULL CHECK (length(resource_type) BETWEEN 1 AND 128),
  resource_id text NOT NULL CHECK (length(resource_id) BETWEEN 1 AND 256),
  consumed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  assertion_expires_at timestamptz NOT NULL CHECK (assertion_expires_at > consumed_at),
  PRIMARY KEY (tenant_id, issuer, nonce)
);
CREATE INDEX request_nonce_ledger_v2alpha2_operation_idx
  ON __SCHEMA__.request_nonce_ledger_v2alpha2 (tenant_id, operation_id);
CREATE INDEX request_nonce_ledger_v2alpha2_expiry_idx
  ON __SCHEMA__.request_nonce_ledger_v2alpha2 (assertion_expires_at);
ALTER TABLE __SCHEMA__.request_nonce_ledger_v2alpha2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE __SCHEMA__.request_nonce_ledger_v2alpha2 FORCE ROW LEVEL SECURITY;
CREATE POLICY request_nonce_ledger_v2alpha2_tenant_isolation
  ON __SCHEMA__.request_nonce_ledger_v2alpha2
  USING (tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
REVOKE ALL ON TABLE __SCHEMA__.request_nonce_ledger_v2alpha2 FROM PUBLIC;
