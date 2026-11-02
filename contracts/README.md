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

## 下一步

生成Package正/负样例、事件类型Schema、完整OpenAPI路径和Contract Test；执行R03.18所列Spike；所有验证报告关联Git commit。
