# Contract Test Fixtures

These fixtures are synthetic and contain no real user or tenant data.

| Fixture | Expected result | Purpose |
|---|---|---|
| experiment-package.valid.json | PASS against experiment-package.schema.v1alpha1.json | Valid Package structure |
| experiment-package.invalid.json | FAIL | Missing required model digest and unsupported runtime mode |
| runtime-event.valid.json | Local Envelope + SessionStarted payload check PASS; CI pending | SessionStarted fixture |
| runtime-event.execution-succeeded.valid.json | Local Envelope + ExecutionSucceeded payload check PASS; CI pending | ExecutionSucceeded fixture |
| runtime-event.observation-recorded.valid.json | Local Envelope + ObservationRecorded payload check PASS; CI pending | ObservationRecorded fixture |
| dc-circuit.reference-cases.json | Automated arithmetic checks in validate_contracts.py; expert review pending | Synthetic DC series-circuit reference cases |
| rc-circuit.reference-cases.json | Analytic reference values; Runtime ODE validation only; expert review pending | RC charging samples at 0, 1, 2 and 5 seconds |
| scientific-model.dc-series.valid.json | Local Draft 2020-12 validation PASS; CI run pending | Synthetic ideal DC ScientificModel |
| observation.valid.json | Local Draft 2020-12 validation PASS; CI run pending | Synthetic scalar Observation |

R03.23 records one-time local execution: Package Schema meta-validation and positive/negative fixtures passed; Runtime Event Schema meta-validation and positive fixture passed. This is not yet a CI run. The repository CI must repeat these assertions with pinned dependencies on every relevant change.

Additional test suites must cover semantic references, digest verification, Package dependency resolution, license policy, model compatibility, event ordering, idempotency and tenant authorization. JSON Schema alone cannot verify these domain-level constraints.


## Scientific Expression AST Fixtures

- `scientific-expression.fixtures.v1alpha1.json`包含欧姆定律、串联电阻、功率和RC电压导数的正向类型样例，以及维度、符号、函数、运算符、除零、非有限数、幂和资源限制负向案例。
- 这些Fixtures由`scripts/validate_expression_ast.py`静态验证；不进行表达式求值。


## Package Resource Graph Fixtures

- `package-resource-graph.fixtures.v1alpha1.json`覆盖Package根、资源节点、依赖边、根可达闭包及外部/受限资源策略。
- 由`scripts/validate_package_resource_graph.py`执行静态图检查；不访问网络或读取外部资源。


## Canonical Manifest Fixtures

- package-canonical-manifest.fixtures.v1alpha1.json包含资源和依赖闭包的规范化Projection，以及路径、重复项、大小写和Unicode负向案例。
- JCS与Deterministic CBOR仅作为比较候选，不代表已选型。


## Package Governance Fixtures

- package-governance.fixtures.v1alpha1.json包含合成信任注册表、Package subject、Provenance、License记录及11个负向策略案例。
- Fixture中的签名字符串仅用于结构和信任策略检查，不是有效密码学签名。
