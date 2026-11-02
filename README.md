# Integrated STEM & Virtual Laboratory Platform

综合 STEM 与虚拟实验室平台。项目文档先行，代码实现须通过产品与架构审计后启动。

## 当前项目状态

- 文档阶段：R01竞品研究、R02产品定义、R03技术架构基线已形成第一轮可审阅文档。
- 审计结论：**条件通过（文档基线）**，不是代码审计或生产就绪结论。
- 代码策略：P3.17及新代码实现继续冻结，直至用户明确解除冻结并按阻断项逐项关闭。
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

### R02 — 产品定义与PRD
| 文档 | 内容 | 状态 |
|---|---|---|
| [R02 产品需求基线](docs/product/R02-product-requirements-baseline.md) | 愿景、角色、旅程、信息架构、功能清单、MVP和验收 | v1.0草案 |

### R03 — 技术方案与架构
| 文档 | 内容 | 状态 |
|---|---|---|
| [R03 技术架构基线](docs/architecture/R03-technical-architecture-baseline.md) | 模块边界、领域模型、Package、API、Runtime、Worker、安全、部署 | v1.0设计基线 |
| [R03.5 跨文档审计与ADR](docs/architecture/R03.5-cross-document-audit-and-adr.md) | 一致性审计、架构决策、阻断项和开发门槛 | v0.1 |

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
- 竞品价格、数量、计划和许可必须记录来源、日期与统计口径。
- 设计基线不等于实现；存在参考代码不等于测试通过。

## 当前已知工程约束

- P3.15参考包曾发现TypeScript编译错误，Vitest未安装，数据库、RLS、NATS、Outbox、Worker集成闭环未验证；不可宣称Runtime Core已完成。
- P3.17暂停；需先完成文档审计和阻断项治理。
- 代码冻结解除后仍需按P0/P1/P2/P3阶段分别实现和验收。

## 版本记录

- 2026-11-02：建立R01研究、R02产品需求、R03技术方案和跨文档审计第一轮文档基线。
