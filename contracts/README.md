# Contracts目录说明

本目录保存机器可读的技术契约草案。文件存在或JSON语法可解析，不代表Schema语义、OpenAPI完整性或运行时兼容性已验证。

| 文件 | 用途 | 状态 |
|---|---|---|
| experiment-package.schema.v1alpha1.json | ExperimentPackage Manifest结构约束 | Draft；需正/负样例与兼容测试 |
| runtime-event-envelope.schema.v1.json | Runtime领域事件信封 | Draft；需事件类型Schema和Consumer测试 |
| openapi.v1.draft.yaml | Session/Command/Observation API骨架 | Draft；需完整响应、错误、安全和Contract Test |

## 使用约束

1. 这些契约是讨论和Spike输入，不得直接标记为生产冻结。
2. 任何字段变化需更新版本、样例、验证器和兼容测试。
3. API认证上下文派生tenant/actor，不允许请求体自行声明。
4. Package必须固定依赖版本和digest；发布后不可变。
5. Event消费者必须支持重复投递和序列号检查。
6. 正式冻结前必须在CI执行Schema/OpenAPI验证，并由产品、架构、安全和数据负责人审阅。

## 自动化验证\n\n- `scripts/validate_contracts.py`：执行Draft 2020-12 Schema元验证、Package正/负样例、Runtime Event样例、OpenAPI YAML基础结构检查，以及DC/RC参考算例检查。\n- `requirements-contract-validation.txt`：固定验证依赖版本。\n- `.github/workflows/contract-validation.yml`：相关契约文件变更时触发GitHub Actions。\n- OpenAPI YAML基础解析不等于OpenAPI 3.1规范验证；该正式验证器尚未纳入。CI执行结果需以GitHub Actions运行记录为准。\n\n## 下一步

生成Package正/负样例、事件类型Schema、完整OpenAPI路径和Contract Test；执行R03.18所列Spike；所有验证报告关联Git commit。

## 测试样例

参见 [examples/README.md](examples/README.md)，包含Package正向/负向JSON样例和Runtime Event样例。样例预期不等于验证器已执行；CI必须实际运行Draft 2020-12验证器并断言PASS/FAIL。
