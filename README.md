# Integrated STEM & Virtual Laboratory Platform

综合 STEM 与虚拟实验室平台。项目采用文档先行策略；代码实现必须通过产品、科学、架构、安全和工程准入审计后启动。

## 当前项目状态

- 文档阶段：R01竞品研究、R02产品定义、R03技术方案与机器可读契约草案已形成第一轮可审阅基线。
- 审计结论：**文档基线有条件通过；Implementation-Ready未通过。**
- 代码策略：P3.17及新业务实现继续冻结，直至阻断项关闭并经用户明确批准。
- 唯一目标仓库：liucaidong/stem-lab；默认分支main。

## 文档导航

### R01 — 全球竞品研究

| 文档 | 内容 | 状态 |
|---|---|---|
| [R01.2 竞品能力矩阵](docs/research/R01.2-competitor-capability-matrix.md) | 产品定位、能力、内容、计算、集成与扩展 | v0.1 |
| [R01.3 证据与来源登记](docs/research/R01.3-competitor-evidence-register.md) | 官方来源、证据等级、来源口径 | v0.1 |
| [R01.4 产品机会假设](docs/research/R01.4-product-opportunity-hypotheses.md) | 差距、机会与定位假设 | v0.1 |
| [R01.5 集成/部署/授权补证](docs/research/R01.5-competitor-integration-deployment-licensing.md) | LTI、Roster、API、SDK、许可和部署 | v0.1 |
| [R01.6 工作流与技术边界验证](docs/research/R01.6-competitor-workflow-validation.md) | 学生/教师流程、数据、API和实测脚本 | v0.1；文档验证 |
| [R01.7 竞品研究结论](docs/research/R01.7-competitive-landscape-conclusions.md) | 竞品分层、定位、差异化假设和MVP | v0.1；阶段性 |
| [R01.8 竞品研究完整性审计](docs/research/R01.8-competitor-research-audit-and-gate.md) | R01覆盖审计、证据缺口和进入R02条件 | v0.1；有条件通过 |

### R02 — 产品定义与PRD

| 文档 | 内容 | 状态 |
|---|---|---|
| [R02 产品需求基线](docs/product/R02-product-requirements-baseline.md) | 愿景、角色、旅程、信息架构、功能清单、MVP和验收 | v1.0草案 |
| [R02.1 产品愿景与定位](docs/product/R02.1-product-vision-positioning.md) | 愿景、定位、价值主张、战略边界和成功指标 | v0.1草案 |
| [R02.2 用户角色与用户旅程](docs/product/R02.2-personas-jtbd-user-journeys.md) | Personas、JTBD、学生/教师/作者/管理员旅程和研究计划 | v0.1；待访谈验证 |
| [R02.3 产品需求规格说明书](docs/product/R02.3-product-requirements-specification.md) | FR需求、业务规则、异常流程、质量属性和验收基线 | v0.1 PRD草案 |
| [R02.4 产品功能树与Capability Map](docs/product/R02.4-product-capability-map.md) | L0-L2能力地图、角色矩阵、能力与技术模块映射 | v0.1 |
| [R02.5 教学MVP范围与发布门禁](docs/product/R02.5-mvp-scope-acceptance-and-release-gates.md) | DC Circuit教学MVP、E2E验收、指标和发布门禁 | v0.1 |
| [R02.6 需求追踪与产品审计](docs/product/R02.6-requirements-traceability-and-audit.md) | 需求—用户价值—能力—架构—验收追踪及R02审计 | v0.1；有条件通过 |
| [R02.7 用户研究执行手册](docs/product/R02.7-user-research-interview-guide.md) | 教师/学生/作者/管理员/采购者访谈、观察任务与记录模板 | v0.1；计划未执行 |
| [R02.8 DC Circuit教学设计](docs/product/R02.8-dc-circuit-learning-design.md) | 学习目标、科学模型、实验序列、仪器语义、误概念和Rubric | v0.1；待学科签核 |
| [R02.9 研究与科学设计补充审计](docs/product/R02.9-research-and-science-design-audit.md) | 新增研究/学科文档审计、证据缺口和产品冻结条件 | v0.1；有条件通过 |
| [R02.10 商业模式与定价假设](docs/product/R02.10-business-model-and-pricing-hypotheses.md) | 客户细分、候选包装、价值度量、成本模型和定价研究 | v0.1；未验证假设 |
| [R02.11 内容供给与质量治理](docs/product/R02.11-content-supply-and-quality-governance.md) | 内容生产生命周期、学科/教学/技术审核、许可和撤回 | v0.1设计草案 |
| [R02.12 试点与客户运营](docs/product/R02.12-pilot-rollout-and-customer-operations.md) | 试点阶段、入驻培训、客户成功、支持分级和退出流程 | v0.1设计草案 |
| [R02.13 产品战略与试点审计](docs/product/R02.13-product-strategy-and-pilot-audit.md) | R02全链路覆盖、一致性、产品冻结阻断项和阶段决策 | v0.1；有条件通过 |
| [R02.14 DC Circuit参考算例](docs/product/R02.14-dc-circuit-reference-cases.md) | 理想串联电路计算样例、边界输入、I-V图语义和专家签核清单 | v0.1；未签核草案 |
| [R02.1–R02.12 平台架构设计系列](docs/architecture/R02.1-R02.12-platform-architecture-series.md) | 总体架构、Model、Runtime、Package、Renderer、Authoring、Data、Learning、AI、Plugin和Infrastructure | v1.0设计基线 |

### R03 — 技术方案与架构

| 文档 | 内容 | 状态 |
|---|---|---|
| [R03 技术架构基线](docs/architecture/R03-technical-architecture-baseline.md) | 模块边界、领域模型、Package、API、Runtime、Worker、安全和部署 | v1.0设计基线 |
| [R03.5 跨文档审计与ADR](docs/architecture/R03.5-cross-document-audit-and-adr.md) | 一致性审计、架构决策、阻断项和开发门槛 | v0.1 |
| [R03.6 产品—技术架构一致性审计](docs/architecture/R03.6-product-architecture-consistency-audit.md) | R02/R03追踪、架构歧义和技术冻结清单 | v0.1；未达Implementation-Ready |
| [R03.7 Runtime状态机与Worker协议](docs/architecture/R03.7-runtime-state-command-worker-protocol.md) | Session状态机、Command事务、幂等、Clock、Lease/Epoch/Fencing | v0.1契约草案 |
| [R03.8 Experiment Package规范](docs/architecture/R03.8-experiment-package-schema-and-release.md) | Manifest、依赖锁定、校验流水线、不可变发布和撤回 | v0.1；Schema待冻结 |
| [R03.9 Scientific Model与Observation契约](docs/architecture/R03.9-scientific-model-and-observation-contracts.md) | 模型定义、单位量纲、DC/RC验证、测量和数据语义 | v0.1；待专家签核 |
| [R03.10 API与事件契约](docs/architecture/R03.10-api-event-contracts.md) | REST/OpenAPI、幂等、错误模型、事件信封和版本策略 | v0.1契约草案 |
| [R03.11 多租户安全与威胁模型](docs/architecture/R03.11-multitenant-security-and-threat-model.md) | IAM/RLS、Worker隔离、Package/AI安全、隐私与威胁登记 | v0.1；待安全/法律审查 |
| [R03.12 部署与质量工程](docs/architecture/R03.12-deployment-quality-and-release-validation.md) | 部署拓扑、CI门禁、测试分层、可观测、备份恢复和发布 | v0.1；待Spike验证 |
| [R03.13 文档体系完整性审计](docs/architecture/R03.13-document-system-audit-and-engineering-gate.md) | R01–R03覆盖审计、Implementation-Ready阻断项和工程准入 | v0.1；未达Implementation-Ready |
| [R03.14 领域数据模型与ERD](docs/architecture/R03.14-domain-data-model-and-erd.md) | 核心实体、关系、事务边界、约束、索引和RLS要求 | v0.1逻辑模型草案 |
| [R03.15 Runtime状态迁移矩阵](docs/architecture/R03.15-runtime-transition-and-command-matrix.md) | 状态迁移、Command权限、并发竞态、不变量和测试向量 | v0.1契约草案 |
| [R03.16 API与事件契约样例](docs/architecture/R03.16-api-event-contract-examples.md) | Session/Command/Observation API、事件信封和错误样例 | v0.1样例 |
| [R03.17 Package Manifest样例](docs/architecture/R03.17-package-manifest-example-and-schema-gate.md) | YAML样例、Schema规则、发布校验和正式Schema门禁 | v0.1样例 |
| [R03.18 技术验证与Spike矩阵](docs/architecture/R03.18-technical-validation-and-spike-matrix.md) | 技术Spike、自动化测试、故障注入、数值验证和证据模板 | v0.1；尚未执行 |
| [R03.19 技术就绪度复审](docs/architecture/R03.19-technical-readiness-review.md) | R03覆盖复审、局部验证证据和工程准入Gate | v0.2；未达Implementation-Ready |
| [R03.20 技术决策登记册](docs/architecture/R03.20-technical-decision-register.md) | 已接受原则、选型候选、产品/合规待决策项和ADR模板 | v0.1；待评审 |
| [R03.21 工程准入WBS](docs/architecture/R03.21-engineering-readiness-wbs.md) | 产品决策、科学验证、契约、Spike、安全和解冻审计工作分解 | v0.2；Run #41/#42 CI成功，持续更新 |
| [R03.22 机器可读契约草案审阅](docs/architecture/R03.22-machine-readable-contract-review.md) | 契约草案审阅、局部机器验证结果与剩余缺口 | v0.2；Draft，局部验证 |
| [R03.23 契约验证执行报告](docs/architecture/R03.23-contract-validation-execution-report.md) | Draft 2020-12 Schema元验证、正负样例及OpenAPI YAML解析执行记录 | v0.1；局部验证通过，契约未冻结 |
| [R03.24 Scientific Model验证计划](docs/architecture/R03.24-scientific-model-verification-plan.md) | DC教学模型不变量、RC解析参考解、Solver收敛/单位/科学签核验收协议 | v0.1；验证计划，专家签核待完成 |
| [R03.25 Model/Observation契约草案审阅](docs/architecture/R03.25-model-observation-contract-draft-review.md) | ScientificModel与Observation Schema、Fixture、语义校验缺口 | v0.1；本地元验证通过，完整语义待完成 |
| [R03.26 Runtime Event Payload契约审阅](docs/architecture/R03.26-runtime-event-payload-contract-review.md) | 三种代表事件Payload Schema、Registry、Fixture和Consumer测试缺口 | v0.1；Schema/Fixture与CI Run #41/#42通过，Consumer测试待完成 |
| [R03.27 PostgreSQL物理模型与RLS草案](docs/architecture/R03.27-postgresql-physical-data-model-and-rls-draft.md) | 物理表分组、复合租户约束、RLS上下文、事务与测试矩阵 | v0.1；候选设计，数据库Spike未执行 |
| [R03.28 OpenAPI安全/幂等/分页审阅](docs/architecture/R03.28-openapi-security-idempotency-pagination-review.md) | JWT与资源授权、幂等、ETag、Cursor、错误模型与限流缺口 | v0.1；OpenAPI 0.3；规范验证及API语义断言Run #49通过 |
| [R03.29 单位与量纲契约草案](docs/architecture/R03.29-unit-dimension-contract-draft.md) | SI核心单位Registry、量纲向量、Model/Observation语义和DC/RC映射 | v0.1；Draft，CI待验证，DEC-08仍OPEN |

### Contracts — 机器可读契约草案

| 文件 | 内容 | 状态 |
|---|---|---|
| [Contracts目录说明](contracts/README.md) | 契约草案使用约束与正式冻结要求 | Draft |
| [Experiment Package JSON Schema](contracts/experiment-package.schema.v1alpha1.json) | Package Manifest结构约束 | Draft；Draft 2020-12元检查及正/负样例通过，CI Run #41/#42通过 |
| [Runtime Event Envelope Schema](contracts/runtime-event-envelope.schema.v1.json) | Runtime事件通用信封结构 | Draft；元Schema与正样例已验证 |
| [Runtime Event Payload Registry](contracts/events/README.md) | SessionStarted/ExecutionSucceeded/ObservationRecorded三种事件Payload Schema | Draft；脚本已接入，CI Run #41/#42通过 |
| [Scientific Model Schema](contracts/scientific-model.schema.v1alpha1.json) | 模型参数、变量、方程引用、约束和求解器需求 | Draft；本地元Schema/Fixture复核通过，基础引用/范围检查已加入 |
| [Observation Schema](contracts/observation.schema.v1alpha1.json) | 观测来源、单位、仿真时间、质量和载荷引用 | Draft；Schema与Package/Model/Quantity绑定语义正负断言通过Run #41/#42/#49 CI；量纲体系待完成 |
| [Unit Registry Schema](contracts/units/unit-registry.schema.v1.json) | 单位登记结构、四维量纲向量、SI比例/偏移 | Draft；待Run #50 CI验证 |
| [SI Core Unit Registry](contracts/units/si-unit-registry.v1.json) | V/A/ohm/W/F/s/dimensionless核心单位 | Draft；待Run #50 CI验证
| [OpenAPI草案](contracts/openapi.v1.draft.yaml) | Session、Command、Observation API请求/响应/错误Schema | Draft v0.3；OpenAPI 3.1规范验证与API语义断言Run #49通过 |
| [Contract Test Fixtures](contracts/examples/README.md) | Package/Event/Model/Observation样例及DC/RC参考算例 | CI Run #41/#42通过；全量版本锁定依赖回归完成 |
| [DC Circuit参考算例JSON](contracts/examples/dc-circuit.reference-cases.json) | DC-001至DC-004理论输入/输出样例 | Draft；自动算术检查已纳入脚本，科学签核待完成 |
| [RC Circuit参考算例JSON](contracts/examples/rc-circuit.reference-cases.json) | RC充电一阶ODE解析参考解；仅作Runtime技术验证 | Draft；非教学MVP，专家签核待完成 |

## 核心产品与架构决策

1. 首个教学MVP：**DC Circuit & Ohm's Law（直流电路与欧姆定律）**。
2. **RC Circuit** 是Runtime/ODE/Scheduler/Worker技术验证案例，不替代教学MVP。
3. Scientific Model、Simulation Runtime、Rendering Engine严格解耦。
4. Experiment Package声明式、可校验、版本化，发布后不可变。
5. Runtime状态变更只能通过Command Handler。
6. 科学计算在独立Worker执行；结果须通过stateVersion、epoch、execution和lease fencing。
7. AI Agent经Tool Gateway和权限策略执行，不直接访问数据库或任意代码环境。
8. 首期架构采用Modular Monolith + Independent Scientific Worker。

## 审计与证据规则

- A：官方技术文档/帮助中心明确说明。
- B：官方产品页或厂商陈述，未独立验证。
- C：可信第三方材料。
- U：公开资料未确认；不得据此断言产品不支持。
- “官方文档验证”不等于“真实产品试用验证”。
- 设计基线不等于实现；Schema可解析不等于契约通过验证；测试文件存在不等于测试通过。

## 当前已知工程约束

- P3.15参考包曾发现TypeScript编译错误，Vitest未安装，数据库、RLS、NATS、Outbox、Worker集成闭环未验证；不可宣称Runtime Core已完成。
- P3.17暂停；需先完成文档审计、契约冻结和技术Spike。
- 代码冻结解除后仍需按Foundation→Package→Model→Runtime→Learning→Integration阶段实现和验收。

### 自动化验证工具

- [契约验证脚本](scripts/validate_contracts.py)
- [直接依赖声明](requirements-contract-validation.txt)
- [全量依赖版本锁定](requirements-contract-validation.lock.txt)
- [GitHub Actions契约验证工作流](.github/workflows/contract-validation.yml)

## 版本记录

- 2026-11-02：补齐R01.8、R02.1–R02.14、R03.6–R03.27、机器可读契约、自动验证脚本/工作流、DC/RC参考算例和科学验证计划。
