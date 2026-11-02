# Contracts目录说明

本目录保存机器可读的技术契约草案。文件存在或JSON语法可解析，不代表Schema语义、OpenAPI完整性或运行时兼容性已验证。

| 文件 | 用途 | 状态 |
|---|---|---|
| experiment-package.schema.v1alpha1.json | ExperimentPackage Manifest结构约束 | Draft；需正/负样例与兼容测试 |
| runtime-event-envelope.schema.v1.json | Runtime领域事件通用信封 | Draft；三种代表事件Payload已另行定义 |
| events/registry.v1.json与events/*.payload.schema.v1.json | 事件类型与Payload Schema映射 | Draft；仅覆盖三种代表事件，Consumer测试待完成 |
| scientific-model.schema.v1alpha1.json | ScientificModel结构契约 | Draft；Schema、引用/范围/单位绑定语义正负断言通过Run #41/#42/#53 CI；完整量纲运算与转换待完成 |
| observation.schema.v1alpha1.json | Observation元数据与数据载荷契约 | Draft；Schema与Package/Model/Quantity绑定语义正负断言通过Run #41/#42 CI；量纲体系待完成 |
| openapi.v1.draft.yaml | Session/Command/Observation API契约 | Draft v0.3；Observation size/time约束及API静态语义断言通过Run #49 |

## 使用约束

1. 这些契约是讨论和Spike输入，不得直接标记为生产冻结。
2. 任何字段变化需更新版本、样例、验证器和兼容测试。
3. API认证上下文派生tenant/actor，不允许请求体自行声明。
4. Package必须固定依赖版本和digest；发布后不可变。
5. Event消费者必须支持重复投递和序列号检查。
6. 正式冻结前必须在CI执行Schema/OpenAPI验证，并由产品、架构、安全和数据负责人审阅。

## 自动化验证

- `scripts/validate_contracts.py`：执行Draft 2020-12 Schema元验证、Package正/负样例、Unit Registry/量纲检查、Package本地Asset真实SHA-256/size、路径穿越/绝对路径/Windows盘符/反斜线路径/缺失文件/symlink逃逸负向检查、Registry驱动Runtime Event Envelope/Payload、Model/Observation样例及单位绑定语义检查、OpenAPI YAML基础结构检查，以及DC参考算例与非法输入/数值边界、RC参考算例与参数/时间序列负向检查（待Run #70确认）。
- `requirements-contract-validation.txt`：声明直接依赖。
- `requirements-contract-validation.lock.txt`：固定Run #42验证过的直接/传递依赖版本；目前未使用hash校验。
- `.github/workflows/contract-validation.yml`：相关契约文件变更时触发GitHub Actions。
- OpenAPI YAML解析与OpenAPI 3.1规范验证是两项不同检查。正式验证器已固定并接入脚本；[openapi-spec-validator 0.9.0官方PyPI页面](https://pypi.org/project/openapi-spec-validator/)说明其支持OpenAPI 3.1/3.2。Run #41/#42/#49/#53/#60均成功：[Run #41](https://github.com/liucaidong/stem-lab/actions/runs/41392312080)、[Run #42](https://github.com/liucaidong/stem-lab/actions/runs/41392380372)、[Run #49](https://github.com/liucaidong/stem-lab/actions/runs/41392793514)、[Run #53](https://github.com/liucaidong/stem-lab/actions/runs/41393149650)、[Run #60](https://github.com/liucaidong/stem-lab/actions/runs/41393457492)、[Run #62](https://github.com/liucaidong/stem-lab/actions/runs/41393629901)、[Run #63](https://github.com/liucaidong/stem-lab/actions/runs/41393682423)、[Run #65](https://github.com/liucaidong/stem-lab/actions/runs/41393825347)、[Run #68](https://github.com/liucaidong/stem-lab/actions/runs/41394380611)、[Run #70](https://github.com/liucaidong/stem-lab/actions/runs/41394526351)。

## 下一步

生成Package正/负样例、事件类型Schema、完整OpenAPI路径和Contract Test；执行R03.18所列Spike；所有验证报告关联Git commit。

## 测试样例

参见 [examples/README.md](examples/README.md)，包含Package正向/负向JSON样例和Runtime Event样例。样例预期不等于验证器已执行；CI必须实际运行Draft 2020-12验证器并断言PASS/FAIL。


## Scientific Expression AST

- `scientific-expression-ast.schema.v1alpha1.json`定义版本化JSON AST结构；
- AST节点只表示常量、符号引用、受限一元/二元运算和白名单函数调用；
- 符号解析必须使用Scientific Model注册表，单位必须来自Unit Registry；
- 静态检查不执行表达式，不是生产求值器或Solver；
- 设计细节见[R03.33](../docs/architecture/R03.33-scientific-expression-ast-and-quantity-type-system.md)。


## Package Resource Graph

- `package-resource-graph.schema.v1alpha1.json`定义版本化资源图结构；
- 所有依赖边必须解析，图必须无环，所有资源必须位于Package根可达闭包；
- 外部资源使用HTTPS主机allowlist，受限资源需要显式访问策略ID；
- 资源图与现有Package Manifest映射仍待集成；静态检查不等于生产发布服务；
- 设计细节见[R03.34](../docs/architecture/R03.34-package-resource-graph-and-dependency-closure.md)。


## Canonical Manifest Projection

- package-canonical-manifest.schema.v1alpha1.json定义摘要输入Projection；
- 资源列表和依赖闭包有独立确定性排序规则；
- 顶层Digest、签名和Attestation不参与自身摘要输入；
- RFC 8785 JCS与RFC 8949 Deterministic CBOR均为候选，DEC-27保持OPEN；
- 详细规则见[R03.35](../docs/architecture/R03.35-canonical-manifest-and-deterministic-package-digest.md)。


## Package Governance

- Attestation绑定Package ID/Version/Digest Profile/Digest；
- Provenance记录构建者、源修订和依赖材料Digest；
- License Record绑定具体Asset Digest及来源/权利/审核证据；
- 静态治理验证不等于密码学验签、真实密钥管理或法律审查；
- 详细规则见[R03.36](../docs/architecture/R03.36-package-signature-provenance-and-license-governance.md)。


## API Security and Operational Semantics

- api-error-catalog.v1alpha1.json定义稳定错误码和重试语义；
- commands目录定义Command Payload Schema与Registry；
- API安全语义验证器测试JWT Claims、资源授权、幂等与Cursor HMAC；
- 真实JWT验签、JWKS、API Middleware和分布式Rate Limit仍未实现。


## Runtime Execution Contract

- runtime-execution-contract.schema.v1alpha1.json定义Execution、Worker Lease、Quota、Clock、Checkpoint与Replay策略；
- 静态验证不执行Worker/Runtime/Solver；
- Simulation Time与Wall-clock Time分离；
- 设计细节见[R03.41](../docs/architecture/R03.41-simulation-runtime-engineering-contract.md)。


## Scientific Solver Verification

- solver-verification-contract.schema.v1alpha1.json定义Solver数值策略契约；
- DC/RC numerical reference harness测试收敛、稳定性、精度、量纲和确定性；
- Euler/RK4仅为测试参考积分器，不是生产Solver；
- 详见[R03.42](../docs/architecture/R03.42-scientific-solver-verification-architecture.md)。


## Visualization and Instrument

- visualization-instrument-contract.schema.v1alpha1.json定义Renderer/Scene/Timeline/Instrument契约；
- Simulation Time与Wall-clock Timeline严格区分；
- 仪表读数必须绑定Observation与Quantity/Unit；
- 静态验证不运行Renderer或真实采样；详见[R03.43](../docs/architecture/R03.43-rendering-visualization-and-instrument-contract.md)。


## Engineering Integration Audit

- engineering-integration-audit.v1alpha1.json记录横向一致性检查、风险和就绪度；
- 审计发现Package Projection、信任链、Tenant隔离、真实Broker、生产Runtime/Solver/Renderer等仍未闭环；
- 结果为CONDITIONAL_NOT_READY，不代表产品或生产环境Ready；
- 详见[R03.44](../docs/architecture/R03.44-engineering-integration-audit.md)。


## Package Resource Catalog Snapshot & Projection Builder

- `package-resource-catalog-snapshot.schema.v1alpha1.json`定义不可变资源目录快照：资源身份、存储、URI、独立Canonical Path、MIME、大小、License和传递依赖。
- `contracts/examples/package-projection-builder.fixtures.v1alpha1.json`提供Manifest + Catalog + Model Expression引用的集成Fixture。
- `scripts/validate_package_projection_builder.py`是验证型参考实现，检查直接引用映射、Expression依赖、闭包、确定性排序和拒绝条件。
- Builder不下载资源、不验证真实内容字节、不签名、不做License法律判断；生产集成未实现。
- 根节点原始Manifest Digest与最终Canonical Package Digest分离，根节点不进入Canonical Projection资源列表，避免自引用。
- 设计边界见 [R03.45](../docs/architecture/R03.45-contract-integration-and-projection-builder-design.md)；AUD-001仍OPEN，DEC-27/28/29仍OPEN。


R03.45验证型参考实现已纳入 `scripts/validate_contracts.py` 的CI入口；[GitHub Actions Run #173](https://github.com/liucaidong/stem-lab/actions/runs/41425774644)通过Manifest/Catalog投影、Model Expression绑定、传递依赖闭包、排序扰动和11个拒绝案例。该结果只证明当前Python参考验证器和Fixture，不代表生产发布器或内容字节验证完成。


最新加固验证为 [GitHub Actions Run #177](https://github.com/liucaidong/stem-lab/actions/runs/41426075633)：11项拒绝案例、ScientificModel spec形状、直接引用唯一性、Canonical Path唯一性/大小写碰撞及依赖闭包通过。生产资源摄取、真实字节Digest、签名和License Enforcement未实现。


## Canonicalization Golden Vectors (R03.46)

- `examples/package-canonicalization-golden-vectors.v1alpha1.json`保存固定JCS/CBOR输入、规范化字节Hex和domain-separated SHA-256期望值。
- `scripts/validate_package_canonicalization_golden_vectors.py`使用固定Python库验证。
- `scripts/verify_package_canonicalization_golden_vectors.mjs`使用Node.js独立实现验证同一组Golden Vectors。
- JCS覆盖UTF-16属性排序/Unicode、数值格式/负零和嵌套数据；CBOR只覆盖Core Deterministic整数/文本/Map/Array/bool/null子集。
- 不代表完整RFC一致性或生产Profile选型；DEC-27仍OPEN，DEC-17/28/29不变。详见 [R03.46](../docs/architecture/R03.46-projection-builder-hardening-and-golden-vectors.md)。


R03.46 Golden Vector CI证据：[Run #183](https://github.com/liucaidong/stem-lab/actions/runs/41427643723)通过Python JCS 3组、CBOR 1组以及独立Node.js 4组验证；所有固定Canonical Bytes和Digest匹配。完整RFC覆盖、CBOR浮点/Tag/byte string/bignum和生产Digest Profile仍未完成。


R03.46 Run #187进一步通过真实Package Projection Builder输出到JCS/CBOR候选序列化链路、顺序扰动确定性和source-manifest-digest自引用隔离：[Run #187](https://github.com/liucaidong/stem-lab/actions/runs/41427937900)。真实Manifest字节Digest核验仍未实现。


## Package Content Integrity & Pinned Catalog Snapshot (R03.47)

- `package-resource-catalog-snapshot.schema.v1alpha2.json`增加snapshot_digest和candidate profile标识。
- `examples/package-content-integrity.fixtures.v1alpha1.json`包含原始Manifest bytes、两个资源字节Fixture及Catalog Snapshot。
- `scripts/validate_package_content_integrity.py`校验源Manifest精确字节Digest/size/身份、资源bytes Digest/size、路径、Catalog依赖引用和Snapshot Digest。
- Catalog Snapshot Digest使用显式字段投影、排序和domain separation；当前JCS仅为candidate profile，不代表DEC-27决策。
- 不含生产文件摄取、对象存储、外部URL解析、归档解压、SSRF防护、签名或License Enforcement。详见 [R03.47](../docs/architecture/R03.47-resource-content-integrity-and-catalog-snapshot-pinning.md)。


R03.47 [Run #193](https://github.com/liucaidong/stem-lab/actions/runs/41428620138)通过：精确Source Manifest字节校验、两个嵌入资源Fixture字节校验、Catalog Snapshot JCS candidate pin、顺序不变性及8项拒绝案例。仍是Fixture-only harness，不是生产摄取/对象存储/外部资源解析。


## Package Archive Ingestion & Quarantine Boundary (R03.48)

- `package-ingestion-policy.schema.v1alpha1.json`定义Archive大小、Entry数量、解压总量、压缩比、压缩方法和路径/Symlink/Encryption策略。
- `scripts/test_package_archive_ingestion.py`在内存中生成和读取ZIP，不写磁盘；验证Manifest与资源Fixture字节绑定。
- 覆盖13项拒绝案例；[Run #199](https://github.com/liucaidong/stem-lab/actions/runs/41428995668)成功。
- 不代表生产隔离区、对象存储、恶意软件扫描、远程解析或安全审计已实现。详见 [R03.48](../docs/architecture/R03.48-package-archive-ingestion-and-quarantine-boundary.md)。


## Package Ingestion Lifecycle (R03.49)

- `package-ingestion-session.schema.v1alpha1.json`定义会话状态、revision、attempt、验证证据和append-only transition log。
- `scripts/validate_package_ingestion_lifecycle.py`校验状态机允许边、状态链、revision、sequence、验证证据、终态原因和幂等语义。
- `validated`只表示结构/字节完整性门禁通过，不表示签名、许可、信任或发布审批通过。
- 生产数据库持久化、上传API、Worker/Lease、Broker和Quarantine Service尚未实现。详见 [R03.49](../docs/architecture/R03.49-package-ingestion-state-machine-and-quarantine-lifecycle.md)。


R03.49 [Run #204](https://github.com/liucaidong/stem-lab/actions/runs/41429361691)通过状态机、revision/sequence、验证证据门禁、终态原因、幂等重放/冲突和10项拒绝案例。该Harness仅验证契约，不代表生产持久化、Worker、Broker或Quarantine Service已实现。


## PostgreSQL Package Ingestion Persistence Harness (R03.50)

- `scripts/test_package_ingestion_postgres.py`在独立PostgreSQL测试Schema验证Session、Transition、Idempotency Receipt和Outbox事务。
- 覆盖原子提交/回滚、幂等重放/冲突、revision竞态、tenant RLS和append-only Transition Ledger。
- 只验证PostgreSQL CI Harness，不是生产迁移或Broker集成；GUC tenant context仍不是独立安全边界。详见 [R03.50](../docs/architecture/R03.50-postgresql-ingestion-transaction-rls-and-outbox-integration.md)。


R03.50 [Run #212](https://github.com/liucaidong/stem-lab/actions/runs/41430210617)通过8项PostgreSQL测试：状态/Receipt/Outbox原子事务、幂等重放/冲突、stale revision、Outbox故障回滚、RLS、append-only ledger和并发revision竞争。测试发现并修复了Receipt FK锁与Session FOR UPDATE的死锁顺序。生产迁移和Broker relay未实现。


## Package Ingestion Worker Lease / Fencing / Retry (R03.51)

- `sql/package-ingestion-worker/R03.51-ingestion-worker.sql` adds tenant-scoped Job and DLQ reference DDL on top of the R03.50 Session schema.
- `scripts/test_package_ingestion_worker_postgres.py` is a disposable PostgreSQL integration harness for concurrent claims, lease expiry/reclaim, epoch fencing, renewal, completion rollback, retry/DLQ, duplicate completion and tenant RLS.
- The SQL is not a production migration. The harness is not a production Worker, scheduler, broker relay or replay service.
- See `docs/architecture/R03.51-ingestion-worker-lease-fencing-retry.md` and the R03.51 verification report.


## R03.51 Package Ingestion Job

- `package-ingestion-job.schema.v1alpha1.json` defines the machine-readable Job envelope and lease/status fields.
- `scripts/validate_ingestion_job_contract.py` validates the Draft 2020-12 schema and representative queued/running/succeeded states.
- `sql/package-ingestion-worker/R03.51-ingestion-worker.sql` is reference DDL only; it assumes R03.50 Session tables and is not a production migration.
- PostgreSQL lease/fencing tests are in `scripts/test_package_ingestion_worker_postgres.py`.

R03.51 PostgreSQL reference evidence: [GitHub Actions Run #41440101768](https://github.com/liucaidong/stem-lab/actions/runs/41440101768) SUCCESS; 20/20 Worker lease/fencing/retry tests passed. This is not production Worker readiness.


## Worker Runtime Lifecycle & Supervision Reference (R03.52.1)

- `runtime/worker_runtime.py` implements an adapter-neutral single-slot orchestration core: claim, handler dispatch, lease heartbeat, fail-closed lease loss, completion/failure requests, and graceful drain.
- `scripts/test_worker_runtime.py` verifies lifecycle semantics with a fake Store. CI execution does not verify PostgreSQL adapter behavior or production process supervision.
- A Store adapter must independently fence every write by tenant, job, owner, epoch and database-clock lease expiry. It must use bounded network/statement timeouts.
- Python is not selected as the production Worker runtime; DEC-03 remains OPEN. DEC-04/05/13/19/30 remain OPEN. See `docs/architecture/R03.52.1-worker-runtime-lifecycle-supervision.md`.


R03.52.1 CI evidence: [GitHub Actions Run #41441940260](https://github.com/liucaidong/stem-lab/actions/runs/41441940260) SUCCESS; 9/9 adapter-neutral Worker Runtime lifecycle tests passed. R03.51 PostgreSQL tests 20/20 and R03.50 PostgreSQL tests 8/8 also passed. No production Store adapter or process supervisor is implied.


## Bounded Worker Poller Pool (R03.52.2)

- runtime/worker_pool.py starts a fixed number of WorkerRuntime poll loops and requires unique worker identities.
- scripts/test_worker_pool.py tests configured concurrency, shutdown fan-out, startup validation and failure propagation using fake pollers.
- This is process-local orchestration. It is not a distributed scheduler, production supervisor, or proof of cross-replica concurrency limits.
- PostgreSQL remains the durable claim authority; no production Store adapter is included.


R03.52.2 CI evidence: [GitHub Actions Run #41442438174](https://github.com/liucaidong/stem-lab/actions/runs/41442438174) SUCCESS; Worker Pool 5/5, Worker Runtime 9/9, R03.51 PostgreSQL 20/20 and R03.50 PostgreSQL 8/8 passed. Worker Pool tests use fake pollers and do not verify cross-replica scheduling or production supervision.


## Process Signal & Graceful Shutdown Bridge (R03.52.3)

- runtime/process_lifecycle.py installs SIGINT/SIGTERM handlers from the main thread; the callback only sets an Event.
- A monitor thread forwards shutdown to WorkerPool, and prior handlers are restored on exit.
- scripts/test_process_lifecycle.py uses a patched signal API and fake Pool; no real process kill or deployment supervisor is exercised.
- The bridge does not enforce a hard shutdown deadline. External orchestration owns termination grace and forced termination; leases are recovered by R03.51 expiry/fencing.


R03.52.3 CI evidence: [GitHub Actions Run #41443126489](https://github.com/liucaidong/stem-lab/actions/runs/41443126489) SUCCESS; Signal Bridge tests 4/4 passed. Earlier failed attempts #41442821982 and #41442974507 are retained and their causes/fixes documented in the R03.21 WBS and R03.20 decision register. This is a patched-signal-API reference test, not container/deployment supervision.


## Worker Error Taxonomy & Retry Policy Registry (R03.52.4)

- worker-retry-policy.schema.v1alpha1.json defines a versioned registry schema; worker-retry-policy.v1alpha1.json is an illustrative candidate, not an approved production policy.
- runtime/retry_policy.py maps stable error codes to safe messages and capped full-jitter decisions; unknown codes fail closed.
- scripts/validate_worker_retry_policy.py checks schema and policy invariants; scripts/test_worker_retry_policy.py verifies behavior.
- The persisted Job attempt_count/maximum_attempts remain authoritative. No production exception classifier, live rollout, signed policy, or DLQ replay is implemented.
