# Runtime Event Payload Schemas

本目录定义Runtime事件类型与其Payload Schema的版本化映射。通用信封位于上级目录的 `runtime-event-envelope.schema.v1.json`。

| Event Type | Schema Version | Payload Schema | Fixture |
|---|---|---|---|
| SessionStarted | 1.0 | session-started.payload.schema.v1.json | runtime-event.valid.json |
| ExecutionSucceeded | 1.0 | execution-succeeded.payload.schema.v1.json | runtime-event.execution-succeeded.valid.json |
| ObservationRecorded | 1.0 | observation-recorded.payload.schema.v1.json | runtime-event.observation-recorded.valid.json |

## 规则

1. 事件必须先通过通用Envelope Schema，再按 `event_type + schema_version` 路由到唯一Payload Schema。
2. 未知事件类型或不支持的破坏性版本必须安全失败并告警；不得把未知Payload当作可信对象继续执行。
3. 新增可选字段优先保持向后兼容；删除字段、改变语义或改变必需字段必须提升Schema版本并提供迁移策略。
4. Consumer仍需处理重复、乱序、序号缺口和重放；Payload Schema不能替代幂等与顺序控制。
5. 当前仅覆盖三种代表事件，不代表R03.10列出的事件类型已全部完成。
6. Payload不得包含访问令牌、任意可执行脚本、未经授权的个人信息或大体积原始数据；大数据使用受控引用和digest。

## 自动化

`scripts/validate_contracts.py`读取 `registry.v1.json`，对Payload Schema执行Draft 2020-12元Schema检查，并验证对应事件Envelope和Payload Fixture。CI成功运行仍需GitHub Actions证据。
