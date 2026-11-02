#!/usr/bin/env python3
"""PostgreSQL integration tests for RLS, transaction boundaries, Inbox/Outbox.
DATABASE_URL must point to a disposable PostgreSQL test database.
"""
from __future__ import annotations
import os,threading,unittest,uuid
import psycopg
from psycopg import errors

DSN=os.environ.get("DATABASE_URL","postgresql://postgres:postgres@localhost:5432/stemlab_test")
SCHEMA="stemlab_r039_"+uuid.uuid4().hex[:10]

def admin():
 return psycopg.connect(DSN,autocommit=True)
def app_conn(tenant=None):
 c=psycopg.connect(DSN)
 with c.transaction():
  c.execute("SET LOCAL ROLE stemlab_app")
  c.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
  if tenant is not None: c.execute("SELECT set_config('app.tenant_id', %s, true)",(tenant,))
 return c

class PostgreSQLContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.a=admin()
  cls.a.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='stemlab_app') THEN CREATE ROLE stemlab_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; END IF; END $$")
  cls.a.execute(f"CREATE SCHEMA {SCHEMA}")
  cls.a.execute(f"""
  CREATE TABLE {SCHEMA}.parents(tenant_id text NOT NULL,parent_id text NOT NULL,PRIMARY KEY(tenant_id,parent_id));
  CREATE TABLE {SCHEMA}.children(tenant_id text NOT NULL,child_id text NOT NULL,parent_id text NOT NULL,PRIMARY KEY(tenant_id,child_id),FOREIGN KEY(tenant_id,parent_id) REFERENCES {SCHEMA}.parents(tenant_id,parent_id));
  CREATE TABLE {SCHEMA}.sessions(tenant_id text NOT NULL,session_id text NOT NULL,state_version int NOT NULL,PRIMARY KEY(tenant_id,session_id));
  CREATE TABLE {SCHEMA}.commands(tenant_id text NOT NULL,session_id text NOT NULL,idempotency_key text NOT NULL,request_hash text NOT NULL,PRIMARY KEY(tenant_id,session_id,idempotency_key));
  CREATE TABLE {SCHEMA}.outbox(id bigserial PRIMARY KEY,tenant_id text NOT NULL,event_id text NOT NULL UNIQUE,payload text NOT NULL,published boolean NOT NULL DEFAULT false);
  CREATE TABLE {SCHEMA}.inbox(tenant_id text NOT NULL,consumer_id text NOT NULL,event_id text NOT NULL,payload_digest text NOT NULL,PRIMARY KEY(tenant_id,consumer_id,event_id));
  CREATE TABLE {SCHEMA}.effects(tenant_id text NOT NULL,consumer_id text NOT NULL,event_id text NOT NULL,PRIMARY KEY(tenant_id,consumer_id,event_id));
  """)
  for table in ("parents","children","sessions","commands","outbox","inbox","effects"):
   cls.a.execute(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")
   cls.a.execute(f"ALTER TABLE {SCHEMA}.{table} FORCE ROW LEVEL SECURITY")
   cls.a.execute(f"CREATE POLICY tenant_isolation ON {SCHEMA}.{table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")
   cls.a.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON {SCHEMA}.{table} TO stemlab_app")
  cls.a.execute(f"GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA {SCHEMA} TO stemlab_app")
  cls.a.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO stemlab_app")
 @classmethod
 def tearDownClass(cls):
  cls.a.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
  cls.a.close()
 def setUp(self):
  with self.a.cursor() as cur:
   for table in ("effects","inbox","outbox","commands","sessions","children","parents"):
    cur.execute(f"DELETE FROM {SCHEMA}.{table}")
 def test_rls_select_is_tenant_scoped(self):
  self.a.execute(f"INSERT INTO {SCHEMA}.parents VALUES ('A','a1'),('B','b1')")
  with app_conn("A") as c:
   rows=c.execute("SELECT parent_id FROM parents ORDER BY parent_id").fetchall()
   self.assertEqual(rows,[("a1",)])
 def test_rls_missing_context_defaults_to_no_rows(self):
  self.a.execute(f"INSERT INTO {SCHEMA}.parents VALUES ('A','a1')")
  with app_conn() as c:
   self.assertEqual(c.execute("SELECT count(*) FROM parents").fetchone()[0],0)
 def test_rls_with_check_rejects_cross_tenant_insert(self):
  with app_conn("A") as c:
   with self.assertRaises(errors.InsufficientPrivilege):
    c.execute("INSERT INTO parents VALUES ('B','b1')")
 def test_composite_foreign_key_blocks_cross_tenant_reference(self):
  self.a.execute(f"INSERT INTO {SCHEMA}.parents VALUES ('B','b1')")
  with app_conn("A") as c:
   with self.assertRaises(errors.ForeignKeyViolation):
    c.execute("INSERT INTO children VALUES ('A','c1','b1')")
 def test_transaction_local_context_does_not_leak_on_connection_reuse(self):
  self.a.execute(f"INSERT INTO {SCHEMA}.parents VALUES ('A','a1'),('B','b1')")
  c=psycopg.connect(DSN)
  try:
   with c.transaction():
    c.execute("SET LOCAL ROLE stemlab_app"); c.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
    c.execute("SELECT set_config('app.tenant_id','A',true)")
    self.assertEqual(c.execute("SELECT count(*) FROM parents").fetchone()[0],1)
   with c.transaction():
    c.execute("SET LOCAL ROLE stemlab_app"); c.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
    self.assertEqual(c.execute("SELECT count(*) FROM parents").fetchone()[0],0)
  finally: c.close()
 def test_command_state_and_outbox_rollback_atomically(self):
  self.a.execute(f"INSERT INTO {SCHEMA}.sessions VALUES ('A','s1',0)")
  with self.assertRaises(RuntimeError):
   with app_conn("A") as c:
    with c.transaction():
     c.execute("UPDATE sessions SET state_version=1 WHERE tenant_id='A' AND session_id='s1'")
     c.execute("INSERT INTO outbox(tenant_id,event_id,payload) VALUES ('A','e1','{}')")
     raise RuntimeError("injected failure")
  self.assertEqual(self.a.execute(f"SELECT state_version FROM {SCHEMA}.sessions WHERE session_id='s1'").fetchone()[0],0)
  self.assertEqual(self.a.execute(f"SELECT count(*) FROM {SCHEMA}.outbox").fetchone()[0],0)
 def test_idempotency_unique_key_rejects_second_request(self):
  with app_conn("A") as c:
   c.execute("INSERT INTO commands VALUES ('A','s1','key-1','hash-1')")
   with self.assertRaises(errors.UniqueViolation):
    c.execute("INSERT INTO commands VALUES ('A','s1','key-1','hash-2')")
 def test_inbox_dedup_and_digest_conflict(self):
  with app_conn("A") as c:
   c.execute("INSERT INTO inbox VALUES ('A','consumer-1','e1','digest-1') ON CONFLICT DO NOTHING")
   c.execute("INSERT INTO inbox VALUES ('A','consumer-1','e1','digest-1') ON CONFLICT DO NOTHING")
   self.assertEqual(c.execute("SELECT count(*) FROM inbox").fetchone()[0],1)
   row=c.execute("SELECT payload_digest FROM inbox WHERE event_id='e1'").fetchone()
   self.assertEqual(row[0],"digest-1")
   with self.assertRaises(errors.UniqueViolation):
    c.execute("INSERT INTO inbox VALUES ('A','consumer-1','e1','digest-2')")
 def test_outbox_claim_uses_skip_locked_for_parallel_relays(self):
  self.a.execute(f"INSERT INTO {SCHEMA}.outbox(tenant_id,event_id,payload) VALUES ('A','e1','{{}}'),('A','e2','{{}}')")
  c1=psycopg.connect(DSN); c2=psycopg.connect(DSN)
  try:
   c1.execute("BEGIN"); c1.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
   c2.execute("BEGIN"); c2.execute(f"SET LOCAL search_path TO {SCHEMA}, public")
   q="SELECT id FROM outbox WHERE published=false ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"
   id1=c1.execute(q).fetchone()[0]; id2=c2.execute(q).fetchone()[0]
   self.assertNotEqual(id1,id2)
   c1.commit(); c2.commit()
  finally: c1.close(); c2.close()
 def test_tenant_rls_applies_to_inbox_and_outbox(self):
  self.a.execute(f"INSERT INTO {SCHEMA}.outbox(tenant_id,event_id,payload) VALUES ('A','eA','{{}}'),('B','eB','{{}}')")
  with app_conn("A") as c:
   self.assertEqual(c.execute("SELECT event_id FROM outbox").fetchall(),[("eA",)])
   self.assertEqual(c.execute("SELECT count(*) FROM inbox").fetchone()[0],0)

if __name__=="__main__":
 unittest.main(verbosity=2)
