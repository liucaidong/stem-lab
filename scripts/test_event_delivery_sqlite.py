#!/usr/bin/env python3
"""SQLite-backed integration harness for durable event delivery semantics.
This is executable persistence/transaction testing, not a PostgreSQL or NATS test.
"""
from __future__ import annotations
import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path

class IntegrityViolation(Exception): pass
class TenantViolation(Exception): pass

class EventStore:
 def __init__(self,path):
  self.path=str(path)
  with self.db() as c:
   c.executescript("""
   CREATE TABLE aggregate_state(tenant_id TEXT, aggregate_id TEXT, last_sequence INTEGER NOT NULL, value INTEGER NOT NULL, PRIMARY KEY(tenant_id,aggregate_id));
   CREATE TABLE outbox(event_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, aggregate_id TEXT NOT NULL, sequence INTEGER NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE broker_messages(message_id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL,tenant_id TEXT NOT NULL,aggregate_id TEXT NOT NULL,sequence INTEGER NOT NULL,digest TEXT NOT NULL,payload TEXT NOT NULL,acked INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE inbox(consumer_id TEXT NOT NULL,event_id TEXT NOT NULL,tenant_id TEXT NOT NULL,aggregate_id TEXT NOT NULL,sequence INTEGER NOT NULL,digest TEXT NOT NULL,processed INTEGER NOT NULL,PRIMARY KEY(consumer_id,event_id));
   CREATE TABLE consumer_cursor(consumer_id TEXT NOT NULL,tenant_id TEXT NOT NULL,aggregate_id TEXT NOT NULL,last_sequence INTEGER NOT NULL,projection_value INTEGER NOT NULL,PRIMARY KEY(consumer_id,tenant_id,aggregate_id));
   CREATE TABLE side_effects(consumer_id TEXT NOT NULL,event_id TEXT NOT NULL,effect TEXT NOT NULL,PRIMARY KEY(consumer_id,event_id));
   CREATE TABLE dlq(event_id TEXT NOT NULL,consumer_id TEXT NOT NULL,reason TEXT NOT NULL,attempts INTEGER NOT NULL,PRIMARY KEY(consumer_id,event_id));
   """)
 def db(self):
  c=sqlite3.connect(self.path,timeout=5,isolation_level=None)
  c.row_factory=sqlite3.Row
  c.execute("PRAGMA foreign_keys=ON")
  return c
 @staticmethod
 def digest(payload): return "sha256:"+hashlib.sha256(payload.encode()).hexdigest()
 def produce(self,event_id,tenant,aggregate,seq,payload,fail_before_commit=False):
  digest=self.digest(payload); c=self.db()
  try:
   c.execute("BEGIN IMMEDIATE")
   row=c.execute("SELECT last_sequence FROM aggregate_state WHERE tenant_id=? AND aggregate_id=?",(tenant,aggregate)).fetchone()
   last=row["last_sequence"] if row else 0
   if seq!=last+1: raise IntegrityViolation("producer sequence must be contiguous")
   c.execute("INSERT INTO aggregate_state VALUES(?,?,?,?) ON CONFLICT(tenant_id,aggregate_id) DO UPDATE SET last_sequence=excluded.last_sequence,value=excluded.value",(tenant,aggregate,seq,seq))
   c.execute("INSERT INTO outbox(event_id,tenant_id,aggregate_id,sequence,digest,payload) VALUES(?,?,?,?,?,?)",(event_id,tenant,aggregate,seq,digest,payload))
   if fail_before_commit: raise RuntimeError("injected producer crash before commit")
   c.commit()
  except Exception:
   c.rollback(); raise
  finally: c.close()
 def relay_one(self,crash_after_broker_accept=False):
  c=self.db()
  try:
   row=c.execute("SELECT * FROM outbox WHERE published=0 ORDER BY rowid LIMIT 1").fetchone()
   if not row: return None
   c.execute("BEGIN IMMEDIATE")
   c.execute("INSERT INTO broker_messages(event_id,tenant_id,aggregate_id,sequence,digest,payload) VALUES(?,?,?,?,?,?)",(row["event_id"],row["tenant_id"],row["aggregate_id"],row["sequence"],row["digest"],row["payload"]))
   if crash_after_broker_accept:
    c.commit()
    raise RuntimeError("injected relay crash after broker acceptance, before outbox mark")
   c.execute("UPDATE outbox SET published=1 WHERE event_id=?",(row["event_id"],))
   c.commit(); return c.execute("SELECT max(message_id) AS id FROM broker_messages").fetchone()["id"]
  except Exception:
   if c.in_transaction: c.rollback()
   raise
  finally: c.close()
 def messages(self,event_id=None):
  with self.db() as c:
   if event_id: return c.execute("SELECT * FROM broker_messages WHERE event_id=? ORDER BY message_id",(event_id,)).fetchall()
   return c.execute("SELECT * FROM broker_messages ORDER BY message_id").fetchall()
 def consume(self,message_id,consumer="projection",allowed_tenant=None,crash_after_commit=False,max_attempts=3):
  c=self.db()
  try:
   c.execute("BEGIN IMMEDIATE")
   msg=c.execute("SELECT * FROM broker_messages WHERE message_id=?",(message_id,)).fetchone()
   if not msg: raise KeyError(message_id)
   if msg["acked"]: c.commit(); return "already-acked"
   if allowed_tenant is not None and msg["tenant_id"]!=allowed_tenant: raise TenantViolation("tenant scope mismatch")
   existing=c.execute("SELECT digest FROM inbox WHERE consumer_id=? AND event_id=?",(consumer,msg["event_id"])).fetchone()
   if existing:
    if existing["digest"]!=msg["digest"]: raise IntegrityViolation("same event_id with different payload digest")
    c.commit()
    if crash_after_commit: return "committed-unacked"
    c.execute("UPDATE broker_messages SET acked=1 WHERE message_id=?",(message_id,))
    return "duplicate"
   payload=json.loads(msg["payload"])
   if payload.get("poison"):
    attempts=msg["attempts"]+1
    c.execute("UPDATE broker_messages SET attempts=? WHERE message_id=?",(attempts,message_id))
    if attempts>=max_attempts:
     c.execute("INSERT OR REPLACE INTO dlq VALUES(?,?,?,?)",(msg["event_id"],consumer,"POISON_EVENT",attempts))
     c.execute("UPDATE broker_messages SET acked=1 WHERE message_id=?",(message_id,))
     c.commit(); return "dead-lettered"
    c.commit(); return "retry"
   cursor=c.execute("SELECT last_sequence,projection_value FROM consumer_cursor WHERE consumer_id=? AND tenant_id=? AND aggregate_id=?",(consumer,msg["tenant_id"],msg["aggregate_id"])).fetchone()
   last=cursor["last_sequence"] if cursor else 0
   if msg["sequence"]>last+1:
    c.rollback(); return "gap"
   if msg["sequence"]<=last:
    c.execute("INSERT INTO inbox VALUES(?,?,?,?,?,?,1)",(consumer,msg["event_id"],msg["tenant_id"],msg["aggregate_id"],msg["sequence"],msg["digest"]))
    c.commit()
    if crash_after_commit: return "committed-unacked"
    c.execute("UPDATE broker_messages SET acked=1 WHERE message_id=?",(message_id,))
    return "stale"
   c.execute("INSERT INTO inbox VALUES(?,?,?,?,?,?,1)",(consumer,msg["event_id"],msg["tenant_id"],msg["aggregate_id"],msg["sequence"],msg["digest"]))
   value=int(payload.get("delta",1))+(cursor["projection_value"] if cursor else 0)
   c.execute("INSERT INTO consumer_cursor VALUES(?,?,?,?,?) ON CONFLICT(consumer_id,tenant_id,aggregate_id) DO UPDATE SET last_sequence=excluded.last_sequence,projection_value=excluded.projection_value",(consumer,msg["tenant_id"],msg["aggregate_id"],msg["sequence"],value))
   c.execute("INSERT INTO side_effects VALUES(?,?,?)",(consumer,msg["event_id"],"projection-updated"))
   c.commit()
   if crash_after_commit: return "committed-unacked"
   c.execute("UPDATE broker_messages SET acked=1 WHERE message_id=?",(message_id,))
   return "processed"
  except Exception:
   if c.in_transaction: c.rollback()
   raise
  finally: c.close()
 def scalar(self,sql,args=()):
  with self.db() as c: return c.execute(sql,args).fetchone()[0]
 def close(self): pass

class EventDeliveryIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.store=EventStore(Path(self.tmp.name)/"events.sqlite")
 def tearDown(self): self.tmp.cleanup()
 def publish(self,event_id="e1",seq=1,payload=None,tenant="t1",aggregate="s1"):
  payload=payload or json.dumps({"delta":1},separators=(",",":"))
  self.store.produce(event_id,tenant,aggregate,seq,payload)
  self.store.relay_one()
  return self.store.messages(event_id)[-1]["message_id"]
 def test_outbox_and_aggregate_update_are_atomic(self):
  with self.assertRaises(RuntimeError): self.store.produce("e1","t1","s1",1,'{"delta":1}',True)
  self.assertEqual(self.store.scalar("SELECT count(*) FROM outbox"),0)
  self.assertEqual(self.store.scalar("SELECT count(*) FROM aggregate_state"),0)
 def test_relay_crash_after_broker_acceptance_causes_safe_duplicate_delivery(self):
  self.store.produce("e1","t1","s1",1,'{"delta":1}')
  with self.assertRaises(RuntimeError): self.store.relay_one(crash_after_broker_accept=True)
  self.store.relay_one()
  msgs=self.store.messages("e1"); self.assertEqual(len(msgs),2)
  self.assertEqual(self.store.consume(msgs[0]["message_id"]),"processed")
  self.assertEqual(self.store.consume(msgs[1]["message_id"]),"duplicate")
  self.assertEqual(self.store.scalar("SELECT count(*) FROM side_effects"),1)
 def test_duplicate_event_is_idempotent(self):
  mid=self.publish()
  self.assertEqual(self.store.consume(mid),"processed")
  self.assertEqual(self.store.consume(mid),"already-acked")
  self.assertEqual(self.store.scalar("SELECT count(*) FROM side_effects"),1)
 def test_same_event_id_different_digest_is_rejected(self):
  mid=self.publish()
  self.store.produce("e1","t1","s1",2,'{"delta":99}')
  with self.store.db() as c: c.execute("INSERT INTO broker_messages(event_id,tenant_id,aggregate_id,sequence,digest,payload) VALUES(?,?,?,?,?,?)",("e1","t1","s1",2,self.store.digest('{"delta":99}'),'{"delta":99}'))
  conflicting=self.store.messages("e1")[-1]["message_id"]
  self.store.consume(mid)
  with self.assertRaises(IntegrityViolation): self.store.consume(conflicting)
 def test_sequence_gap_waits_then_recovers(self):
  m1=self.publish("e1",1); self.store.produce("e2","t1","s1",2,'{"delta":2}'); self.store.relay_one(); m2=self.store.messages("e2")[0]["message_id"]
  # Deliver seq=2 first by testing it before seq=1.
  self.assertEqual(self.store.consume(m2),"gap")
  self.assertEqual(self.store.scalar("SELECT last_sequence FROM consumer_cursor"),None)
  self.assertEqual(self.store.consume(m1),"processed")
  self.assertEqual(self.store.consume(m2),"processed")
  self.assertEqual(self.store.scalar("SELECT last_sequence FROM consumer_cursor"),2)
 def test_commit_before_ack_crash_redelivery_does_not_repeat_side_effect(self):
  mid=self.publish()
  self.assertEqual(self.store.consume(mid,crash_after_commit=True),"committed-unacked")
  self.assertEqual(self.store.scalar("SELECT acked FROM broker_messages WHERE message_id=?",(mid,)),0)
  self.assertEqual(self.store.consume(mid),"duplicate")
  self.assertEqual(self.store.scalar("SELECT count(*) FROM side_effects"),1)
 def test_replay_same_event_is_deduplicated(self):
  mid=self.publish(); self.store.consume(mid)
  with self.store.db() as c: c.execute("INSERT INTO broker_messages(event_id,tenant_id,aggregate_id,sequence,digest,payload) SELECT event_id,tenant_id,aggregate_id,sequence,digest,payload FROM outbox WHERE event_id='e1'")
  replay=self.store.messages("e1")[-1]["message_id"]
  self.assertEqual(self.store.consume(replay),"duplicate")
  self.assertEqual(self.store.scalar("SELECT count(*) FROM side_effects"),1)
 def test_poison_event_has_bounded_retry_and_dlq(self):
  mid=self.publish(payload='{"poison":true}')
  self.assertEqual(self.store.consume(mid,max_attempts=3),"retry")
  self.assertEqual(self.store.consume(mid,max_attempts=3),"retry")
  self.assertEqual(self.store.consume(mid,max_attempts=3),"dead-lettered")
  self.assertEqual(self.store.scalar("SELECT count(*) FROM dlq"),1)
  self.assertEqual(self.store.scalar("SELECT acked FROM broker_messages WHERE message_id=?",(mid,)),1)
 def test_cross_tenant_delivery_is_rejected(self):
  mid=self.publish(tenant="tenant-A")
  with self.assertRaises(TenantViolation): self.store.consume(mid,allowed_tenant="tenant-B")
  self.assertEqual(self.store.scalar("SELECT count(*) FROM side_effects"),0)
 def test_ack_is_not_written_when_consumer_transaction_fails(self):
  mid=self.publish(payload='not-json')
  with self.assertRaises(json.JSONDecodeError): self.store.consume(mid)
  self.assertEqual(self.store.scalar("SELECT acked FROM broker_messages WHERE message_id=?",(mid,)),0)
  self.assertEqual(self.store.scalar("SELECT count(*) FROM inbox"),0)

if __name__=="__main__":
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(EventDeliveryIntegrationTests)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 raise SystemExit(not result.wasSuccessful())
