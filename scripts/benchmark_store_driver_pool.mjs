import fs from "node:fs";
import { performance } from "node:perf_hooks";
import pg from "pg";

const { Pool } = pg;
const env = JSON.parse(fs.readFileSync(process.env.STORE_BENCH_ENV_FILE, "utf8"));

function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(p * sorted.length) - 1)];
}

function summarize(concurrency, repetition, latencies, acquireWaits, elapsed) {
  const ms = (value) => Number((value * 1000).toFixed(3));
  return {
    driver: "node-postgres-pg-pgpool",
    concurrency,
    repetition,
    operations: latencies.length,
    throughput_ops_per_second: Number((latencies.length / elapsed).toFixed(2)),
    latency_ms: {
      p50: ms(percentile(latencies, 0.5)),
      p95: ms(percentile(latencies, 0.95)),
      p99: ms(percentile(latencies, 0.99)),
    },
    pool_acquire_wait_ms: {
      p50: ms(percentile(acquireWaits, 0.5)),
      p95: ms(percentile(acquireWaits, 0.95)),
      p99: ms(percentile(acquireWaits, 0.99)),
    },
  };
}

const pool = new Pool({
  ...env.node_config,
  max: env.pool_max,
  min: env.pool_min,
  connectionTimeoutMillis: 10000,
  idleTimeoutMillis: 10000,
  maxLifetimeSeconds: 60,
  pipeline: false,
});

async function operation(token) {
  const started = performance.now();
  const client = await pool.connect();
  const acquired = performance.now();
  let reusable = true;
  try {
    await client.query("BEGIN");
    await client.query('SET LOCAL ROLE "' + env.runtime_role + '"');
    await client.query(
      "SELECT set_config($1, $2, true)",
      ["app.tenant_assertion", token],
    );
    const query = 'SELECT row_id FROM "' + env.schema + '".tenant_rows WHERE row_id = $1';
    const result = await client.query(query, ["a1"]);
    if (result.rows.length !== 1 || result.rows[0].row_id !== "a1") {
      throw new Error("Unexpected RLS result: " + JSON.stringify(result.rows));
    }
    await client.query("COMMIT");
  } catch (error) {
    try {
      await client.query("ROLLBACK");
    } catch {
      reusable = false;
    }
    if (!reusable) client.release(true);
    throw error;
  } finally {
    if (reusable) client.release();
  }
  const ended = performance.now();
  return {
    latency: (ended - started) / 1000,
    acquire: (acquired - started) / 1000,
  };
}

async function runCase(concurrency, repetition) {
  const token = env.tokens[repetition + ":" + concurrency];
  if (!token) throw new Error("Missing assertion token for benchmark case");
  await Promise.all(Array.from({ length: 10 }, () => operation(token)));
  const total = concurrency * env.iterations_per_worker;
  let cursor = 0;
  const latencies = [];
  const acquireWaits = [];
  const started = performance.now();

  async function worker() {
    while (true) {
      const index = cursor++;
      if (index >= total) return;
      const result = await operation(token);
      latencies.push(result.latency);
      acquireWaits.push(result.acquire);
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()));
  const elapsed = (performance.now() - started) / 1000;
  return summarize(concurrency, repetition, latencies, acquireWaits, elapsed);
}

try {
  const results = [];
  for (let repetition = 1; repetition <= env.repetitions; repetition += 1) {
    for (const concurrency of env.concurrency_levels) {
      results.push(await runCase(concurrency, repetition));
    }
  }
  fs.writeFileSync(process.env.STORE_BENCH_NODE_OUTPUT, JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
} finally {
  await pool.end();
}
