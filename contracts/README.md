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


R03.45验证型参考实现已纳入 `scripts/validate_contracts.py` 的CI入口；[GitHub Actions Run #173](https://github.com/liucaidong/stem-lab/actions/runs/41425774644)通过Manifest/Catalog投影、Model Expression绑定、传递依赖闭包、排序扰动和8个拒绝案例。该结果只证明当前Python参考验证器和Fixture，不代表生产发布器或内容字节验证完成。
