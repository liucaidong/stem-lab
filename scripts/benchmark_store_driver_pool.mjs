import fs from "node:fs";
import { performance } from "node:perf_hooks";
import pg from "pg";

const { Pool } = pg;
const env = JSON.parse(fs.readFileSync(process.env.STORE_BENCH_ENV_FILE, "utf8"));
const concurrencyLevels = [1, 8, 32];
const iterationsPerWorker = 80;

function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(p * sorted.length) - 1)];
}

function summarize(concurrency, latencies, acquireWaits, elapsed) {
  const ms = (value) => Number((value * 1000).toFixed(3));
  return {
    driver: "node-postgres-pg-pgpool",
    concurrency,
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
    environment: "GitHub-hosted ephemeral runner; smoke only",
  };
}

const pool = new Pool({
  ...env.node_config,
  max: 16,
  connectionTimeoutMillis: 10000,
  idleTimeoutMillis: 10000,
  maxLifetimeSeconds: 60,
  pipeline: false,
});

async function operation() {
  const started = performance.now();
  const client = await pool.connect();
  const acquired = performance.now();
  let reusable = true;
  try {
    await client.query("BEGIN");
    await client.query('SET LOCAL ROLE "' + env.runtime_role + '"');
    await client.query(
      "SELECT set_config($1, $2, true)",
      ["app.tenant_assertion", env.token],
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

async function runCase(concurrency) {
  await Promise.all(Array.from({ length: 10 }, () => operation()));
  const total = concurrency * iterationsPerWorker;
  let cursor = 0;
  const latencies = [];
  const acquireWaits = [];
  const started = performance.now();

  async function worker() {
    while (true) {
      const index = cursor++;
      if (index >= total) return;
      const result = await operation();
      latencies.push(result.latency);
      acquireWaits.push(result.acquire);
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()));
  const elapsed = (performance.now() - started) / 1000;
  return summarize(concurrency, latencies, acquireWaits, elapsed);
}

try {
  const results = [];
  for (const concurrency of concurrencyLevels) {
    results.push(await runCase(concurrency));
  }
  fs.writeFileSync(process.env.STORE_BENCH_NODE_OUTPUT, JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
} finally {
  await pool.end();
}
