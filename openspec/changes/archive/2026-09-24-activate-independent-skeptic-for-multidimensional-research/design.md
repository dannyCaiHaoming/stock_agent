## Context

现有真实持仓产品入口已经能够从 `PortfolioHandoff v3` 和 `CouncilRequest v2` 建立 `MULTI_DIMENSIONAL_HOLDING_RESEARCH`，冻结同一 cutoff 的 Evidence，派发 Company Analyst 与 Market Catalyst，并归集 `HoldingResearchBundle/2.0.0`。该阶段的 manifest、prompt 和 Skill 明确禁止启动 Skeptic、CIO 或 Risk；其 `DOWNSTREAM_READY` 当前主要以兼容 Company Research 是否已纳入为门槛，仍需在新阶段入口补充核心多维覆盖检查。

仓库同时已有 `runtime_skeptic`、`counter-thesis`、`CounterThesisReport/2.0.0`、run-scoped output schema、严格 Evidence Closure、一次格式修复和 Gate-scoped Evidence 查询能力。这些能力目前服务 fixture/旧 live Council 兼容链路，输入和产物位置假设单一 focus security，不能直接声明已支持多维持仓研究后的逐证券反证。

本设计遵循 Proposal 和三个 delta spec，只增加一个显式研究阶段，不恢复已退役的 `live-us-equity` 产品入口，也不扩展到 CIO、Risk 或回测。

## Goals / Non-Goals

**Goals:**

- 让用户从同一确认 Handoff 选择一次“正向多维研究 + 独立反证”的完整研究运行。
- 在同一 run/cutoff/Gate 内复用现有多维研究实现，并为每只合格普通股生成真实、隔离的 Skeptic Invocation。
- 形成可机器验证的正反研究交接包，使未来 CIO 无需猜测报告绑定或从目录自行发现产物。
- 用新的 MRVL 宿主真实运行证明正向研究、输入隔离、反证产物和停止边界。

**Non-Goals:**

- 不实现 `runtime_cio`、Risk、动作、目标仓位、最终组合建议或网页决策展示。
- 不实现 Outcome 自动采集、历史 point-in-time 重建、Execution Replay、回测、Regression、Ablation 或 Promotion。
- 不增加新研究 Agent，不启用 `TARGETED_PRESSURE_TEST`，不让 Skeptic 阅读正向结论。
- 正向研究本身保持客观；独立首轮研究公司特定失败路径及替代解释，不要求逐条反驳未见过的 Analyst claim，也不要求与正向研究观点不同。
- 不修复所有免费来源的固有限制；专项报告可如实保留 `SOURCE_LIMITED`，但适用核心研究不得以缺报告状态进入反证。

## Decisions

### 1. 新增组合阶段，而不是改变现有多维阶段的默认停止点

增加 `INDEPENDENT_COUNTER_THESIS_RESEARCH` 作为 `CouncilRequest v2` 的显式 stage。该 stage 在一个全新 run 中复用现有资料准备和多维研究 phase，确定性完成正向 bundle 后，再进入 Skeptic phase。原 `MULTI_DIMENSIONAL_HOLDING_RESEARCH` 的默认停止点和用户语义保持不变；共享交付接缝及单股提示规则可按第 9 节修复并做旧阶段回归，不自动启动 Skeptic，不改写历史产物。

这样既能保证正反材料共享同一 run/cutoff/Gate，又避免修改已经归档和展示中的历史多维运行。备选方案是以子运行引用一个既有 bundle；该方案会引入跨 run Evidence、路径与不可变性处理，并容易重新出现当前 v2/v4 混拼问题，因此不采用。

### 2. Skeptic 在正向 bundle 校验后启动，但不接收 bundle 内容

阶段顺序为：

1. 数据准备与 PIT Gate；
2. 既有正向多维研究与 bundle finalizer；
3. 独立反证前置校验；
4. 逐普通股 Skeptic 派发与验证；
5. 正反研究交接包 finalizer。

Skeptic 等待正向 bundle 只是一项阶段门禁，用来避免为不可交付的正向运行继续消耗模型；其输入从原始 Handoff/Request 技术绑定和 Gate Evidence 单独构造。构造器不得读取 bundle/report 正文、摘要、问题或 hash。输入使用精确字段白名单，递归隔离检查仅作为第二道防线。

备选方案是让 Skeptic 与全部正向 Agent 同时启动。它同样可以满足信息隔离，但会在正向核心任务失败时产生无用模型消耗，也增加宿主并发和 Hook 证明复杂度；首版不采用。

### 3. 逐证券 Evidence 范围由 Gate 和确定性数据语义决定

每个 Skeptic Invocation 的允许集合由当前 Gate 中以下 Evidence 的并集构成：

- `security_id` 为目标普通股的公司、行情、技术、所有权、期权及相关材料 Evidence；
- 明确标记为共享 Macro 或 Market 的 Evidence；
- 本次冻结资料中与目标证券具有明确比较关系的同行公开事实；同行同时是另一持仓不构成拒绝理由，但其私人组合字段仍禁止进入输入；
- 为理解上述事实所必需并已在 Gate 内的证券身份和确定性计算 Evidence。

构造器不得查看正向报告实际引用集合来筛选或排序 Evidence，也不得把与目标及同行比较无关的其他公司资料、成本、浮亏、数量、现金或其他个人组合字段交给 Skeptic。`research_question` 和可选 `holding_horizon` 可以进入输入，但必须来自原始用户请求的非结论性研究范围，不能转抄 Agent 结论或夹带持仓金额；资料不足或语义含混时保留限制，不由确定性层改写投资判断。

同行关系来自本次冻结的资料准备映射，不读取正向报告引用集合；材料由 Agent 选择时保留这一来源限制，不宣称资料全集无选择偏差。确定性计算仅开放经本次 Gate 输入闭合、cutoff/hash 校验的数值与方法，不开放报告解释或任意附件路径。研究中发现资料缺口时只记录待补证据，首版不扩张冻结 Gate 或启动额外网络发现。

现有 `CounterThesisReport/2.0.0` 的 `assumption_ids` 没有对应定义，不能直接视为足够。本阶段使用 `CounterThesisReport/2.1.0`，最小增加报告本地 `assumptions`（每项包含唯一 `assumption_id` 与非空 `statement`），逐项校验 challenge 的引用，不允许未定义 ID。假设不等于事实 Evidence；挑战中的事实性断言仍须有 Evidence 支持，纯情景须明确标为假设。传导逻辑与推翻条件沿用现有 statement、resolution_evidence_needed、invalidation_conditions 表达，不增加独立论证图。旧 2.0.0 产物保留按锁定版本读取的路径，不重写历史。报告与目标证券的绑定通过逐证券 Invocation、交接索引和执行证明保存。

当前 live MCP 使用单一 focus 和固定 Agent 文件路径；实施必须将其扩展为通过可信 dispatch index 解析 `(run_id, task_name, invocation_id, security_id)`，以对应 Invocation 的允许集合执行查询，不能仅验证属于全局 Gate。计算读取沿用现有受限工具接缝。测试必须覆盖同一 runtime_skeptic 的两只证券互相越权、其他 Invocation 身份冒用及任意路径拒绝。

### 4. 使用有界逐证券派发，不新增调度器

在现有主线程和 Hook 机制上增加稳定的逐证券任务映射，每个任务绑定 `agent_type=runtime_skeptic`、唯一 task name、Invocation ID、run-scoped schema 和输出路径。并发沿用当前研究阶段上限，先保存全量计划，再按空位补充；持仓数量不成为 Schema 上限。

输出建议放在：

- `research/skeptic/dispatch-index.json`
- `research/skeptic/invocations/<security-slug>.json`
- `research/skeptic/reports/<security-slug>/counter-thesis.json`
- `research/skeptic/reports/<security-slug>/counter-thesis.md`
- `research/skeptic/execution-proof.json`

复用现有 Invocation、run-scoped Evidence enum、Agent/Skill hash、一次格式修复和 `validate_skeptic_report`，只扩展其逐证券路径与 Hook 绑定。禁止新建 Python LLM 编排后端。

### 5. 增加轻量 `PreDecisionResearchPackage/1.0.0`

新交接对象只保存下游需要的绑定和引用：

- package/run/Portfolio/Handoff/Request/cutoff/Gate 身份；
- 正向 `HoldingResearchBundle` 路径和 hash；
- 每只普通股的 Counter Thesis 路径、hash、Invocation、领域状态及技术校验状态；
- 全持仓 coverage、`STRUCTURALLY_CONSUMABLE` 或 `DOWNSTREAM_READY`；
- artifact refs、同源摘要和 package hash。

它不复制 claims/challenges，不生成共识、冲突裁决、置信度聚合或动作。`DOWNSTREAM_READY` 要求正向研究就绪且每只适用普通股具有合法 `COMPLETE` 或已完成研究但置信度低的 `LOW_CONFIDENCE` 报告；它不表示观点正确、Eval PASS 或候选晋升。`INSUFFICIENT_EVIDENCE` 与 `TIMEOUT` 报告可以合法保存和读取，但整体最多为 `STRUCTURALLY_CONSUMABLE`，并列明未完成反证或资料缺口。宿主超时未返回合法报告属于执行未完成，不能由 Python 补写领域报告。系统错误、缺失证券、跨 run/cutoff 或悬空 Evidence 同样阻止下游就绪。非普通股明确保留覆盖排除，普通股研究就绪不表示完整组合决策输入就绪。

中文交付包含可打开的正向报告和逐证券反证正文：原始挑战、依据、假设、传导解释、待补证据与失效条件。交接索引只列状态与引用，渲染器忠实展示 Agent 内容，不另做 LLM 综合或自动冲突裁决；本 Change 不扩建网页。

直接把 Counter Thesis 字段加入 `HoldingResearchBundle/2.0.0` 的方案会改变既有正向包语义并迫使历史包迁移，因此不采用。

### 6. 阶段终态只证明研究完成，不复用完整 Council 终态

run manifest 持续记录 `complete_portfolio_decision=false`，`downstream_stages_started` 只记录实际到达的研究 phase，且禁止出现 CIO/Risk。阶段成功需要正向核心研究合法、正向 bundle 就绪、全部适用普通股具有已完成研究的合法 Counter Thesis、交接包和执行证明闭合。超时和证据不足保留为部分交接，不因 JSON 合法宣称研究完成；系统失败单独保留，不伪装成 `SAFE_NO_TRADE`。

本 Change 不生成 `decision.json`、不调用完整 Council `check-run` 或 Runtime Eval。聚焦确定性检查验证 Schema、绑定、PIT、隔离、Evidence Closure、路径、hash、Agent 生命周期和越界产物缺失。

### 7. MRVL 验收使用新的宿主真实运行

实施完成后通过既有宿主 launcher 启动一次全新 MRVL `INDEPENDENT_COUNTER_THESIS_RESEARCH`。运行必须重新冻结本次数据并在同一 run 中形成正向和反向产物；旧 v2/v4 仅用于说明为何不能拼接，不进入验收包。

验收读取底层产物确认：

- Company、Technical、Fundamental/Event、Industry、Macro、Market 的适用核心报告不存在 `FAILED`、`TIMEOUT`、`NOT_RESEARCHED` 或依赖阻塞；
- 专项能力可保留真实 `SOURCE_LIMITED`；
- Skeptic 输入不含任何正向报告内容或 hash，且至少有一次非空 Gate-scoped Evidence 查询；
- `PreDecisionResearchPackage` 可追溯全部引用并为 `DOWNSTREAM_READY`；
- 没有 CIO、Risk、decision、Outcome 或回测产物。

非空查询是执行真实性检查，不能代替研究质量。独立人工复核须对照原始 Evidence 检查挑战是否公司特定、事实支持是否恰当、传导逻辑是否明确、假设是否诚实标注，以及什么可观察事实会推翻挑战。允许独立研究后未发现强反证，只要报告说明查了什么、限制在哪里；不以挑战数量、观点与 Analyst 不同或股价表现为通过条件，也不新增自动语义分数或 Runtime Eval。

### 8. 恢复仅续跑同一冻结运行的未完成任务

复用现有恢复入口，重验 run、Handoff、Request、cutoff、Gate、版本锁和成功产物 hash 后，只续跑未完成或失败任务；正向研究及成功 Skeptic 不重复运行。新尝试使用独立 Invocation/attempt 绑定与输出路径，保留旧失败和工具事件，不覆盖成功报告。在现有任务映射中最小补充尝试及采用结果引用，不另建重试调度器；每次恢复每个目标任务最多一个新研究尝试，纯格式修复另沿用一次上限。冻结输入或版本锁发生变化时必须新建运行。真实验收先用一个 MRVL 样本，失败后允许显式有界修复和续跑，不自动扩张样本集合。

### 9. 先修正向交付与失败收尾，不扩大研究重试

2026-09-23 MRVL v4/v5 的原始草案表明：宏观 Evidence ID 存在字符错误或中间片段缺失；v5 技术与市场草案遗漏 `run_id`、`invocation_id`、`agent`；结束识别依赖草案 Invocation 导致失败任务仍可能计为运行中，父流程最终超时。Macro 提示及 Skill 无条件要求比较两只持仓，也与单股 MRVL 输入冲突。这些是当前修复依据，不把历史记录中的“未查询证据”推断当成已证实原因。

最小实现边界如下：

1. **执行结束不等于报告成功。** 沿用派发许可、Start 的可信子会话/任务绑定与最终 Stop/执行结果识别终止，不依赖模型返回身份字段。格式修复仍在进行时不能提前视为终止。最终失败须释放并发槽位、保留失败原因；所有任务结束或依赖阻塞后收尾，不继续空等。只有已验证成功报告满足下游依赖。宿主超时保存已有成功产物和未完成清单，不补造领域报告或生命周期事件。
2. **身份由可信上下文封装。** 仅当 run、parent/child session、task、Invocation、Agent/model 的派发和启动映射唯一且验证通过时，确定性层可补齐草案缺失的技术身份。模型显式身份若与映射冲突，或映射缺失/多义，则拒绝；禁止根据正文、证券名称或相近 ID 猜测。原始草案不变，封装结果与绑定来源单独可追溯，正文、状态和证据不改写。
3. **引用使用精确标识。** 优先沿用工具返回的完整 Evidence ID，统一派发 schema、工具输出与提交说明；不先建设通用引用服务。如仍需短引用，只允许本 Invocation 内预先冻结、可追溯的一对一映射，并在最终报告中还原为完整 ID，再执行原 Evidence/PIT 门禁。未知、截断、错拼、跨 Invocation 或歧义标识必须拒绝，禁止模糊纠错、删除主张凑通过。引用属于允许集合与实际查询行为分别核验，不从 closure 错误推断查询缺失，也不把允许目录当作已读事实。
4. **单股研究不强迫第二持仓。** 单股 Macro/Market 解释该公司对宏观与市场条件的敏感性、假设和反向情景；多股才要求比较持仓差异。同行比较仅使用既有授权冻结资料，缺第二只持仓本身不是资料不足原因。Prompt 与 Skill 同步，真实资料不足仍诚实保留。

继续保留一次纯格式修复及原有显式有界恢复，不新增补查询再提交、自动研究重试、新 Agent、第二套调度器或放宽门禁。技术身份封装不属于替 Agent 修改研究结论；可疑 Evidence 引用不能借“格式修复”静默替换。

实施与验收顺序为：终止识别与身份绑定 → 单股规则与精确引用交付 → 脱敏失败样例的确定性回归及不 mock 正向门禁的集成验证 → 新的 MRVL 宿主真实验收。已有 257 项测试结果仅保留为历史证据；新增失败组合已纳入后续 323 项聚焦测试，确定性样例验证不属于 Execution Replay。版本改变后使用新的 v9 运行，没有修补 v4/v5 冒充完成；具体结果和失败沿革见本 Change 的实施验收记录。

## Risks / Trade-offs

- [同一 Gate 的 Evidence 数量较大，Skeptic 可能检索成本较高] → 按确定性语义和 security_id 限定允许集合，保留共享 Macro/Market，但不根据正向报告做相关性过滤；真实运行记录 token 与工具调用，首版不建设检索排序系统。
- [正向 bundle 当前 `DOWNSTREAM_READY` 门槛不足以代表核心报告齐全] → 新阶段入口增加核心 coverage 门禁，不回写或改变历史 bundle 的既有状态。
- [逐证券 Skeptic 增加真实模型消耗和等待时间] → 沿用三槽有界并发、只在正向研究通过后启动，先验收一个 MRVL 样本，复用同次运行成功结果；不自动运行 Regression/Ablation。
- [合法报告被误当研究完成] → 超时及证据不足只能部分交接；MRVL 验收同时核对实际研究内容与技术绑定，低置信度保留理由且不等同系统失败。
- [未来 CIO 输入可能需要调整交接对象] → 首版只输出引用和标准报告，不预先修改 CIO Schema；下一 Change 以该包为输入时再确定 CIO 消费契约。

## Migration Plan

1. 增加新 stage 枚举、请求构造与产品 Skill 说明，不改变现有 stage 默认行为。
2. 增加 Skeptic phase 的 Schema、准备、派发、Hook 保存、验证和研究阶段 finalizer，并为新产物配置版本锁。
3. 增加 `PreDecisionResearchPackage/1.0.0` Schema、验证器和同源渲染器。
4. 使用确定性 fixture/临时目录覆盖正常、输入污染、跨 run/cutoff、悬空 Evidence、混合资产、领域状态和越界 CIO/Risk 产物。
5. 通过宿主 launcher 执行新的 MRVL 真实纵向样本并独立只读复核。

回滚时移除新 stage 的对外选择和新阶段代码/Schema/version binding；既有 `MULTI_DIMENSIONAL_HOLDING_RESEARCH`、历史 bundle 和旧运行目录不需迁移或改写。新运行产物按其锁定版本保持只读可审计。
