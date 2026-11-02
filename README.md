# Integrated STEM & Virtual Laboratory Platform

综合 STEM 与虚拟实验室平台。项目文档先行，代码实现须通过产品与架构审计后启动。

## 文档状态

> 当前阶段：R01 全球竞品研究（进行中）  
> 工程策略：冻结 P3.17 及后续代码实现；先完成研究、PRD、功能清单、总体技术方案与一致性审计。  
> 文档状态：第一批 R01 基线已建立，仍需后续补充与复核。

## 文档导航

| 编号 | 文档 | 状态 |
|---|---|---|
| R01.2 | [全球竞品深度能力矩阵](docs/research/R01.2-competitor-capability-matrix.md) | v0.1 初稿 |
| R01.3 | [竞品证据与来源登记册](docs/research/R01.3-competitor-evidence-register.md) | v0.1 初稿 |
| R01.4 | [竞品差距与产品机会假设](docs/research/R01.4-product-opportunity-hypotheses.md) | v0.1 初稿 |
| R01.5 | [竞品集成、部署、授权与扩展能力补证](docs/research/R01.5-competitor-integration-deployment-licensing.md) | v0.1 初稿 |

## 研究与设计原则

1. 区分教学虚拟实验、交互式科学模拟、科学建模、专业工程仿真、内容平台和创作生态。
2. 对每项能力标注证据状态：官方明确、官方宣传待验证、公开资料未确认、分析推断。
3. 厂商自报的数量、效果、覆盖率和性能指标不作为独立验证结论。
4. 竞品研究用于形成产品决策，不以功能堆叠代替产品定位。
5. Model、Simulation Runtime、Experiment Package、Renderer、Data、Learning、AI Agent、Plugin 保持职责边界。
6. 文档审计通过前不启动新的工程实现，不将设计稿表述为已实现能力。

## 产品目标（工作定义）

建设一套可组合、可扩展、可验证的综合 STEM 学习与科学实验平台，覆盖科学知识、科学模型、数值仿真、实验编排、2D/3D交互、数据分析、学习评价、AI辅助探究、真实设备接入与数字孪生。

## 当前已知工程约束

- 首个教学 MVP 历史决策：DC Circuit & Ohm's Law（直流电路与欧姆定律）。
- RC Circuit 是 Runtime / Solver / Worker 技术验证案例，不替代教学 MVP。
- P3.15 参考包审计发现 TypeScript 编译错误，且数据库、消息总线、Outbox、Worker 等集成闭环尚未得到验证；不得宣称 Runtime Core 已完成。
- P3.17 暂停，等待产品与总体技术文档审计通过。

## 版本记录

- 2026-11-02：建立文档优先基线与 R01 第一批研究文档。
