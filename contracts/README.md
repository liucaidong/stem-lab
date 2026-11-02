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
- OpenAPI YAML解析与OpenAPI 3.1规范验证是两项不同检查。正式验证器已固定并接入脚本；[openapi-spec-validator 0.9.0官方PyPI页面](https://pypi.org/project/openapi-spec-validator/)说明其支持OpenAPI 3.1/3.2。Run #41/#42/#49/#53/#60均成功：[Run #41](https://github.com/liucaidong/stem-lab/actions/runs/41392312080)、[Run #42](https://github.com/liucaidong/stem-lab/actions/runs/41392380372)、[Run #49](https://github.com/liucaidong/stem-lab/actions/runs/41392793514)、[Run #53](https://github.com/liucaidong/stem-lab/actions/runs/41393149650)、[Run #60](https://github.com/liucaidong/stem-lab/actions/runs/41393457492)、[Run #62](https://github.com/liucaidong/stem-lab/actions/runs/41393629901)、[Run #63](https://github.com/liucaidong/stem-lab/actions/runs/41393682423)、[Run #65](https://github.com/liucaidong/stem-lab/actions/runs/41393825347)。

## 下一步

生成Package正/负样例、事件类型Schema、完整OpenAPI路径和Contract Test；执行R03.18所列Spike；所有验证报告关联Git commit。

## 测试样例

参见 [examples/README.md](examples/README.md)，包含Package正向/负向JSON样例和Runtime Event样例。样例预期不等于验证器已执行；CI必须实际运行Draft 2020-12验证器并断言PASS/FAIL。
