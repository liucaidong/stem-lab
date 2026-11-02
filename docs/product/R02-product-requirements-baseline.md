# R02 产品定义与PRD基线

- 版本：1.0；日期：2026-11-02
- 状态：产品基线草案，需用户/教师试点验证
- 关联：R01竞品研究；R03技术架构

## 1. 愿景与定位

建设一套连接科学知识、科学模型、实验活动、数值仿真、交互可视化、数据分析、学习评价和AI辅助探究的综合STEM平台。不是3D动画库、单一虚拟实验网站或专业CAE软件的简单教育版。

## 2. 用户与客户

| 角色 | 任务 | 核心对象 |
|---|---|---|
| 学生 | 探索、预测、操作、测量、分析、解释 | Experiment、Session、Observation、Notebook |
| 教师 | 课程组织、实验布置、过程监控、评价 | Course、Assignment、Report、Rubric |
| 内容作者 | 创建模型、场景、仪器、流程和评价 | Package、Model、Scene、Workflow |
| 机构管理员 | 身份、班级、许可、数据治理和集成 | Tenant、Identity、Roster、Policy |
| 平台运营者 | 内容审核、资源、安全和插件治理 | Catalog、Runtime、Plugin |
| AI Agent | 在授权范围内辅助实验与分析 | Tool Call、Session、Observation |

购买者与使用者可能不同，学校采购、教师工作流和学生体验必须分别验证。

## 3. 设计原则

1. Scientific Model ≠ Simulation Runtime ≠ Renderer。
2. Experiment Package声明实验意图和资源，不嵌入任意不受控代码。
3. Runtime状态只能通过Command Handler变更。
4. 科学计算与交互帧率解耦。
5. 数据携带单位、时间、来源和模型版本。
6. 可复现结果记录Package、Model、Solver和参数版本。
7. AI Agent只能经Tool Gateway执行授权操作。
8. 默认最小权限；真实设备操作需人工确认和安全联锁。
9. 学习评价同时评结果、过程和论证。
10. 开放扩展不等于任意代码执行。

## 4. 首个教学MVP：DC Circuit & Ohm's Law

### 学习目标
- 理解电压、电流、电阻的关系；
- 根据电路结构预测电流变化；
- 操作电源、电阻、开关和测量仪器；
- 采集电压/电流观测；
- 使用表格/图表分析数据；
- 以证据支持结论。

### MVP范围
- 直流电源、理想电阻、导线、开关；
- 简单串联电路；
- 电压表、电流表；
- 变量调节、运行/暂停/重置；
- 欧姆定律代数模型；
- Observation、数据表和I-V图；
- 假设、实验记录、结论和教师评分。

### 明确不做
电磁场有限元、非线性半导体/晶体管级SPICE、任意复杂电路、实体设备控制、VR/AR、多人实时共同编辑、服务器任意代码执行。

### 技术验证案例
RC Circuit单独验证ODE求解、步长策略、Simulation Clock、Worker隔离、调度、epoch fencing、失败恢复和结果提交。它不是教学MVP范围扩张理由。

## 5. 核心用户旅程

### 学生
进入课程实验→阅读目标与安全提示→提交预测→配置模型/变量→运行/暂停/单步/重置→使用仪器采集Observation→查看图表→记录结论→提交报告→接收反馈。

### 教师
创建课程班级→选择实验包版本→配置截止时间/尝试次数/分组/Rubric→发布任务→监控进度→审阅轨迹与数据→评分反馈→导出成绩。

### 作者
创建Package草稿→绑定Model/Scene/Instrument/Workflow/Rubric→配置变量单位约束→Schema/语义校验→Sandbox预览→审核→发布不可变版本。

### 管理员
配置OIDC/SAML/LTI→导入Roster→设定数据保留和导出策略→分配许可/计算配额→审计日志和安全告警。

## 6. 信息架构

- 学生端：Home、My Courses、Experiment Catalog、Experiment Workspace（Brief/Hypothesis、Model/Scene、Controls/Instruments、Timeline、Data/Charts、Notebook、Submission）、Feedback。
- 教师端：Dashboard、Courses/Classes、Assignments、Live Monitor、Student Work、Rubrics/Gradebook、Reports/Export。
- 作者端：Author Studio、Package Editor、Model Registry、Scene/Instrument Editor、Workflow Designer、Validation/Sandbox、Review/Release。
- 管理端：Organization、Users/Roles、SSO/LTI/Roster、Data Governance、Runtime Quotas、Audit/Security、Integrations/Plugins。
- 运营端：Content Moderation、Model/Solver Registry、Runtime Fleet、Plugin Registry、Observability/Incident。

## 7. 功能需求与优先级

P0=教学MVP；P1=平台化首轮；P2=后续扩展。

| 域 | 功能 | 优先级 | 验收 |
|---|---|---:|---|
| Identity | 登录、租户上下文、授权 | P0 | 越权读取被拒绝 |
| Course | 课程、班级、成员、作业 | P0 | 教师仅操作授权课程 |
| Catalog | 实验包目录、版本、发布状态 | P0 | 发布版本不可变 |
| Package | Manifest/Model/Scene/Instrument/Workflow/Rubric引用 | P0 | Schema失败不可发布 |
| Model | 参数、变量、方程、单位、约束 | P0 | 量纲/边界校验 |
| Runtime | Session及Start/Pause/Resume/Reset/Step | P0 | 非法状态转换被拒绝 |
| Command | 幂等键、请求哈希、stateVersion | P0 | 同key同hash重放receipt；异hash冲突 |
| Scheduler | Execution、lease、epoch、clock | P0（RC验证） | 旧epoch结果拒绝 |
| Solver | DC代数模型、RC ODE验证 | P0 | 参考算例在批准容差内 |
| Instrument | Voltmeter/Ammeter | P0 | 读数含单位、精度、来源 |
| Observation | 离散/时间序列观测 | P0 | 可追溯Session和Execution |
| Visualization | 2D电路图、表格、I-V图 | P0 | 显示单位、时间、有效性 |
| Notebook | 假设、步骤、记录、结论 | P0 | 提交快照不可被后续编辑覆盖 |
| Assessment | Rubric、评分、反馈 | P0 | 评分绑定提交版本 |
| Teacher UI | 班级进度、状态、提交查看 | P0 | 权限与刷新策略明确 |
| Author Studio | Package编辑、校验、Sandbox | P1 | 不可信内容不进入生产Runtime |
| Analytics | CSV/JSON导出 | P1 | 导出包含Schema/单位/元数据 |
| LMS | LTI 1.3 Launch/Deep Linking/AGS | P1 | 每项服务独立声明支持 |
| Roster | OneRoster导入同步 | P1 | 幂等更新用户/班级/选课 |
| SSO | OIDC/SAML | P1 | 身份映射与注销可审计 |
| AI | Tool Gateway、审批、审计 | P1 | 作用域/限流/撤销 |
| Plugin | 签名、权限、版本审核 | P2 | 未批准插件不可执行 |
| 3D | 三维场景和物理交互 | P2 | Renderer不拥有科学状态 |
| Remote Lab | 预约、控制权、联锁 | P2 | 安全联锁优先于Agent |
| Digital Twin | 设备映射与校准 | P2 | 状态和误差可追溯 |
| VR/AR | 沉浸交互 | P2 | 需独立学习价值论证 |

## 8. 非功能需求

- 一致性：同一Session命令有序，旧epoch结果拒绝。
- 可复现：固定模型/求解器/输入/数值策略，按声明容差验证。
- 安全：租户隔离、RBAC/ABAC、最小权限、输入校验、审计。
- 可观测：日志/指标/Trace关联tenant/session/execution。
- 可访问：键盘可操作、语义标签、非颜色状态提示。
- 兼容：优先现代桌面浏览器，移动端按实验声明。
- 性能SLO不预设虚构数值，基准测试后冻结。

## 9. MVP验收

学生进入DC实验；Package和Model版本通过校验；创建Session；调整电源/电阻并运行；仪表显示带单位结果；命令、状态和Observation持久化；完成至少两组参数实验并生成I-V数据；提交假设/数据/结论；教师查看过程与提交；重复请求不重复写入；Worker失败/重复消息/旧epoch不能造成状态倒退。

## 10. 成功指标（试点建立基线）

实验启动成功率、首屏时间、运行稳定性、完成率、概念前后测、过程数据完整率、结果可复现率、教师批改耗时、作者创建周期、单次实验成本、AI越权拦截率。试点前不虚构目标数值。
