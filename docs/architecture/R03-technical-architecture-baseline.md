# R03 技术方案与架构基线

- 版本：1.0；日期：2026-11-02
- 状态：设计基线，不代表已实现/已部署
- 架构风格：Modular Monolith + Independent Scientific Worker

## 1. 技术栈候选

| 层 | 候选 | 理由 | 验证项 |
|---|---|---|---|
| Web | TypeScript + React | 交互与生态 | 无障碍、性能 |
| API | TypeScript模块化应用 | 契约与类型协作 | 框架、验证器、OpenAPI |
| Scientific Worker | Python | 科学计算生态 | 隔离、性能、部署 |
| Database | PostgreSQL | 事务、JSONB、RLS | 迁移、连接池、RLS测试 |
| Event Bus | NATS JetStream | 异步事件与确认 | 去重、重放、保留 |
| Object Storage | S3兼容 | 大型数据/模型资产 | 本地/云兼容 |
| Cache | Redis（可选） | 缓存、限流 | 不作权威状态 |
| Observability | OpenTelemetry | Trace/Metric/Log | Collector与后端 |
| Local Dev | Docker Compose | 开发一致性 | Apple Silicon与CI |

以上为候选，不是已安装或验证的技术事实。版本通过ADR和锁文件冻结。

## 2. 逻辑架构

~~~mermaid
flowchart TB
  UI[Student / Teacher / Author UI] --> API[Web BFF / API]
  API --> IAM[Identity & Tenant]
  API --> APP[Application Modules]
  APP --> CAT[Catalog / Experiment Package]
  APP --> LEARN[Course / Assignment / Assessment]
  APP --> RT[Runtime Session / Command]
  RT --> DB[(PostgreSQL)]
  RT --> OUTBOX[Transactional Outbox]
  OUTBOX --> BUS[(NATS JetStream)]
  BUS --> SCH[Scheduler]
  SCH --> WORKER[Scientific Worker]
  WORKER --> SOLVER[Solver Registry]
  WORKER --> OBJ[(Object Storage)]
  WORKER --> RESULT[Result Commit API]
  RESULT --> RT
  APP --> DATA[Observation / Analytics]
  APP --> AI[AI Tool Gateway]
  APP --> INT[Integration Adapters]
  INT --> LMS[LTI / OneRoster / OIDC / SAML]
  RENDER[Renderer] -. commands and read models .-> API
~~~

## 3. 核心模块和依赖规则

- Identity & Tenant：身份映射、租户上下文、授权。
- Catalog/Package：实验包目录、版本、审核、发布。
- Scientific Model：模型元数据、变量、单位、方程和约束。
- Runtime：Session生命周期、状态、命令、事件。
- Scheduler：时钟、Execution、lease/epoch/fencing。
- Worker/Solver：计算任务、求解器注册、输入输出验证。
- Observation/Data：观测、时间序列、文件、导出。
- Learning：课程、班级、作业、笔记、提交、评价。
- Renderer：2D/3D呈现，不拥有权威科学状态。
- AI Tool Gateway：工具授权、参数校验、审批、审计。
- Integration：LTI、OneRoster、OIDC/SAML、外部计算和设备适配。
- Plugin：扩展清单、签名、沙箱和权限策略。

Renderer不得直接写Runtime数据库；Model不拥有Session生命周期；Runtime不实现具体求解算法；Worker不自行改变Session权威状态；AI不得持有DB凭证或任意Worker执行权限；外部厂商API只能经Adapter进入。

## 4. 核心领域实体

Tenant、User、Identity、Membership、RoleBinding、Course、Class、Enrollment、ExperimentPackage、PackageVersion、PackageDependency、ScientificModel、ModelVersion、ModelArtifact、Scene、Instrument、Workflow、Rubric、Assignment、ExperimentInstance、RuntimeSession、RuntimeState、RuntimeCommand、CommandReceipt、RuntimeEvent、Execution、WorkerLease、Observation、ObservationSeries、Snapshot、LabNotebook、Submission、Assessment、FileAsset、Plugin、IntegrationConnection、AuditRecord。

关系：Assignment固定引用已发布Package版本；ExperimentInstance代表一次业务运行；RuntimeSession代表一次可暂停/恢复/重置执行；Session锁定不可变Package依赖；Execution是一次Solver计算尝试；Observation引用Session、Execution、ModelVersion、变量和单位；Submission引用过程快照、Notebook版本和Rubric版本。

## 5. Runtime事务边界

同一命令事务内：设置tenant上下文→锁Session→检查Idempotency-Key和request hash→校验If-Match/stateVersion→验证状态转换→更新Session/State→写Event→写CommandReceipt→写Transactional Outbox→Commit。

科学求解在事务外运行。结果提交单独执行，必须校验input stateVersion、epoch、execution_id、lease和Validator结果。

## 6. Session、时钟与Worker可靠性

Session状态基线：
created→ready→running→paused→resuming→running；running→completed/failed；failed可按显式策略retry/reset。

时钟分离：
- Wall Clock：业务时间；
- Monotonic Clock：进程耗时；
- Simulation Clock：科学模型时间；
- Render Clock：画面刷新；
- Device Clock：真实设备采样时间。

Renderer FPS不等于Simulation Step。Scheduler决定执行时机和步长策略；Solver决定数值求解策略。

Lease/Epoch/Fencing：
- Scheduler获取有过期时间的Lease；
- 接管/恢复时递增epoch；
- Worker结果携带session_id、execution_id、input_state_version、epoch和lease token；
- 旧epoch、过期lease、版本不匹配结果拒绝；
- fencing token必须单调递增，不能只依赖Worker本地时钟。

结果提交条件：Execution仍有效、epoch匹配、输入stateVersion匹配、lease有效、Solver成功、Validator接受、Schema/单位/范围/模型不变量通过。

故障处理：Worker崩溃后lease过期重调度；重复消息按event_id/command_id幂等；乱序按aggregateSequence检测；Solver超时保持最近有效状态；无效输出不推进Simulation Clock；对象存储失败不标记完成。

## 7. Experiment Package契约

逻辑目录：
~~~text
experiment-package/
  manifest.yaml
  learning-objectives.yaml
  model/
  scene/
  instruments/
  workflow/
  assessment/
  assets/
  locales/
  tests/
~~~

Manifest草案字段：apiVersion、kind、metadata(id/version/title/subject/gradeBand)、spec.learningObjectives、model引用、scene引用、instruments、workflow、assessment、runtime modes/resetPolicy。

校验层级：Syntax→Schema→Reference→Semantic（变量/单位/端口）→Safety→Runtime Preflight→Scientific Validation。

发布版本不可变；依赖锁定版本或digest；Session保存完整解析依赖清单；撤回版本不得删除历史学习记录。Package不执行任意脚本。

## 8. API与事件契约

REST/JSON作为首期候选；OpenAPI作为HTTP契约源；写请求Idempotency-Key；并发更新If-Match/stateVersion；时间戳RFC3339 UTC，科学时间另存simulation_time和unit；cursor分页；稳定错误码和correlation_id。

API草案：
- POST /v1/experiment-instances
- POST /v1/sessions
- GET /v1/sessions/{id}
- POST /v1/sessions/{id}/commands
- GET /v1/sessions/{id}/events
- GET /v1/sessions/{id}/observations
- POST /v1/sessions/{id}/submissions
- GET /v1/submissions/{id}
- POST /v1/submissions/{id}/assessment

tenant_id和actor_id必须从认证上下文派生，不能由请求JSON自报。

事件信封字段：eventId、eventType、schemaVersion、tenantId、aggregateType、aggregateId、aggregateSequence、stateVersion、epoch、occurredAt、correlationId、payload。消息至少一次投递，消费者幂等；JetStream去重不替代业务幂等。

## 9. 集成边界

- LTI 1.3：Launch、Deep Linking、Assignment and Grade Services分别声明。
- OneRoster：Roster导入/同步。
- OIDC/SAML：机构身份联邦和SSO。
- SIS/LMS：课程、班级、成员、作业和成绩映射。
- Simulation API：外部计算服务Adapter。
- Device Adapter：设备协议、预约、控制权、安全联锁。
- Plugin API：版本化能力声明和权限范围。

## 10. 安全与数据治理

Authentication采用OIDC优先；Authorization采用RBAC+ABAC；PostgreSQL启用并强制RLS；应用DB角色不得BYPASSRLS；每事务设置transaction-local tenant context；后台任务使用最小权限身份。

Worker非root、只读基础镜像、CPU/内存/时间限制、默认网络拒绝。Package做内容扫描和Schema验证，不执行任意代码。Secrets不入库、不写日志。

平台可能处理未成年人学习记录。上线前须完成适用司法辖区的法律/隐私审查。最低要求：数据最小化、处理目的明确、数据导出/更正/删除、保留策略、管理员访问审计、供应商DPA、数据区域和跨境评估。生产数据不得用于模型训练，除非独立明确授权并审批。

AI经Tool Gateway调用ReadExperimentState、SetAllowedParameter、Start/Pause/Step、ReadObservations、GenerateChart、DraftConclusion、SubmitForReview（需确认）。禁止直接DB访问、任意Shell/Python、越权读其他学生数据和绕过安全联锁。

## 11. 部署与运维

Development：Docker Compose运行API、PostgreSQL、NATS、S3兼容存储、Worker、OTel Collector。

Production候选：无状态API多副本；Scheduler通过lease协调；Worker按队列/Solver能力扩展；PostgreSQL高可用和PITR；NATS持久化；Object Storage版本/生命周期/备份；OTel采集与告警。

备份：PostgreSQL全量+WAL/PITR；Object Storage版本化/复制/digest校验；NATS定义副本、保留和重放窗口。RPO/RTO需基于业务和成本评估，不虚构数值。

关键指标：API latency/error、Session命令延迟、Scheduler queue age/lease失败、Worker耗时/timeout/OOM/solver失败、Outbox backlog、consumer lag、Observation读写、对象存储吞吐、tenant quota。

## 12. 技术选型和待验证事项

React/TypeScript、Python Worker、PostgreSQL、NATS JetStream、S3兼容存储、Redis可选、OpenTelemetry、Docker Compose为候选组合。需做技术Spike：TypeScript/Python协议、科学计算基准、Worker隔离、NATS故障语义、RLS连接池安全、对象存储大文件、浏览器渲染性能和Mac开发环境兼容性。
