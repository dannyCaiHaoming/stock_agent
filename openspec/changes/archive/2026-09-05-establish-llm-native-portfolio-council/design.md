## Context

项目目前是仅包含 OpenSpec 初始化结构的 greenfield 仓库，没有既有产品代码或能力规格。设计需要同时约束 Codex 中的开发协作方式、产品运行时的多 Agent 研究流程，以及未来的离线学习优化流程。相关动机见 `proposal.md`，行为要求见本 Change 下的八项 capability specs。

系统面向投资研究和组合建议，不面向交易执行。其主要复杂度来自事实时点、证据血缘、LLM 与确定性程序的职责分离、多 Agent 上下文隔离、硬风控不可绕过，以及模型和 Skill 版本变化后的可重复评估。

## Goals / Non-Goals

**Goals:**

- 形成可在 Codex Agent Package 中运行的 CIO 主线程、专业 Skills、少量 runtime Agent 和只读 MCP 组合。
- 让每项能力都能独立验证输入、证据、结构化输出和质量，而不依赖“Agent 角色数量”。
- 在历史时点重建系统当时真正可见的数据、模型配置和完整决策路径。
- 让确定性 Risk Engine 对所有建议动作实施最终且不可绕过的硬约束。
- 建立只能提出 Improvement Proposal 的受控学习闭环。

**Non-Goals:**

- 不接入券商、真实账户、订单路由、自动交易或模拟成真实执行的接口。
- MVP 不支持做空、杠杆、期权、期货、盘中高频或多市场跨币种组合。
- 不把主观投资观点、公司质量判断或市场择时逻辑编码为大型 Python 规则引擎。
- 不在本 Change 中选定具体首发市场、数据供应商、模型或风险阈值数值。
- 不允许学习面自动编辑生产 Skill、Agent 配置、Schema 或 Risk Policy。

## Decisions

### 1. 使用三平面物理隔离

仓库按开发控制面、产品运行面和学习优化面组织：

```text
root/
+-- AGENTS.md
+-- .codex/agents/dev_*.toml
+-- openspec/
+-- tests/
+-- evals/
+-- reviews/
+-- product/
|   +-- AGENTS.md
|   +-- .codex-plugin/plugin.json
|   +-- .codex/agents/runtime_*.toml
|   +-- skills/
|   +-- mcp/
|   +-- contracts/
|   +-- deterministic/
|   +-- evidence_store/
+-- learning/
    +-- decision_traces/
    +-- human_feedback/
    +-- market_outcomes/
    +-- reflection_proposals/
    +-- replay/
    +-- promotion/
```

根 `AGENTS.md` 管理开发、OpenSpec、测试和评审；`product/AGENTS.md` 管理实际研究运行。运行时 Agent 不继承开发写权限。学习面通过只读 Trace 和追加式反馈生成建议，其输出只能由开发控制面消费。

替代方案是让所有 Agent 共享根级规则，通过 prompt 约定角色。该方案容易发生权限和指令泄漏，无法可靠证明 runtime Agent 没有生产修改能力，因此不采用。

### 2. 采用 Capability-first，而不是 Agent-first

每项 Capability 以统一合同注册：

```text
Input -> Tool/Data -> Skill/Reasoning -> Structured Output -> Eval
```

Skill 表达可复用研究方法和停止条件；Agent 只在需要专业上下文、独立观点或并行处理时承载一个或多个能力。新增 Agent 必须通过相对现有组合的消融评估。

MVP 默认只包含：

- `runtime_company_analyst`：公司质量和估值能力。
- `runtime_market_catalyst`：行情、流动性、事件与催化剂能力。
- `runtime_skeptic`：独立反证和草案压力测试能力。

估值不是独立 Agent，而是 Company Analyst 使用的专业 Skill 加确定性计算能力。组合风险不是 Agent，而是 Risk Engine。

替代方案是按基金团队岗位一次性建立宏观、行业、量化、情绪、技术、估值和风险 Agent。该方案会产生大量上下文、重复研究和无法证明价值的角色，因此不采用。

### 3. Codex 主线程担任 CIO

`portfolio-council` Skill 在用户提交持仓后建立运行上下文，并让当前主线程承担 CIO 职责。CIO 持有 Portfolio Snapshot、Mandate、用户问题、研究截止时点和所有专业报告，负责：

1. 验证输入和读取前置风险预检。
2. 识别当前决策需要的 Capability。
3. 动态并行委派专业 Agent。
4. 比较证据、共识、冲突和数据缺口。
5. 形成 Council Draft Decision。
6. 接受 Risk Engine 最终校验。
7. 必要时根据可行边界修订一次。
8. 输出 Final Decision Plan 或 `NO_TRADE`。

CIO 不直接覆盖专业 Agent 的原始报告，也不能覆盖 Risk Engine 的否决。

### 4. 第一轮研究隔离，第二轮定向反证

专业 Agent 第一轮在彼此隔离的上下文中研究，减少锚定和群体一致性。Skeptic 第一轮看不到 Company Analyst 或 CIO 的结论；CIO 汇总后可以把明确的 Draft Thesis 交给 Skeptic 做第二轮压力测试。

所有 Agent 通过结构化 Artifact 交换信息，不依赖自由文本聊天记录作为唯一接口。CIO 必须显式记录冲突如何影响结论、仓位范围或 `NO_TRADE`。

### 5. Evidence Store 采用 Fact、Claim、Artifact 三层模型

`FactEnvelope` 至少包含：

- `fact_id`, `security_id`, `field_or_statement`, `value`, `unit`
- `source_id`, `source_type`, `source_locator`
- `as_of`, `retrieved_at`, `source_version_or_hash`
- `freshness_status`, `quality_flags`

`Claim` 引用 Fact，或者明确标记为 Assumption。Agent Research Report、Council Draft、Risk Report 和 Final Decision 都作为带公共信封的 Artifact 保存，公共信封包含 `schema_version`、`artifact_id`、`run_id`、`trace_id`、producer 与输入 Artifact IDs。

Evidence Store 追加新版本而不覆盖旧记录。外部 MCP 只读查询产生的原始响应由受控运行基础设施自动形成 Evidence Artifact；Agent 自身不能任意重写证据。

替代方案是只保存报告中的 URL 和自然语言引用。该方案无法处理后续数据修订、来源版本和 point-in-time Replay，因此不采用。

### 6. Python 只实现确定性服务

Python 范围包括：

- Security Master 映射与数据标准化。
- 财务、行情和事件数据适配。
- 数学指标、估值公式和敏感性计算。
- 持仓、现金、权重、敞口、换手和交易成本核算。
- freshness、Schema、Evidence Closure 和一致性验证。
- Risk Engine 硬约束。
- Evidence Store、Decision Trace 和 Replay 存储。

LLM 范围包括商业质量、估值假设解释、事件意义、Thesis、Counter Thesis、证据冲突、置信度和组合综合。Python 可以计算“在增长率 X 下的估值”，但不能通过隐藏分数决定“公司值得买入”。

### 7. Risk Engine 使用同一 Policy 的两阶段协议

前置预检在研究前输出组合现状和可行边界，减少 CIO 形成明显不可行计划。后置检查使用相同 policy version 对完整草案计算建议前后指标。

Risk Result 为：

- `APPROVED`：所有硬约束满足。
- `REVISE_REQUIRED`：存在可通过收缩范围修复的违规，并返回 feasible bounds。
- `REJECTED`：输入、数据质量或硬约束使建议不可接受。

Risk Engine 不调整 Thesis，也不自动选择替代证券。`REVISE_REQUIRED` 最多触发一次 CIO 修订；第二次仍不合规则输出 `NO_TRADE` 或移除相应交易意图。

### 8. 输出交易意图，不输出可执行订单

Final Decision Plan 使用 `BUY / ADD / HOLD / TRIM / EXIT / NO_TRADE`，包含目标仓位范围而非伪精确单点，并包括：

- 当前与目标仓位范围、最大建议名义金额和时间范围。
- Thesis、Counter Thesis、冲突处理和未解决不确定性。
- Evidence References 与可观察 Invalidation Conditions。
- 建议前后组合指标和完整 Risk Result。
- `advisory_only: true`。

`NO_TRADE` 使用标准原因码，包括输入无效、证据不足、数据过期、实质冲突、低置信度、Mandate 违规、流动性限制和风险否决。

### 9. Decision Trace 是运行和学习的共同主键

每次运行创建稳定 `run_id` 和 `trace_id`，记录输入、委派、工具调用、Evidence、各 Agent 输出、CIO 草案、修订、风险结果和最终输出。Trace 同时锁定模型快照、Skill、Agent 配置、Schema、MCP Adapter、Risk Policy 和数据快照版本。

Replay 根据 `retrieved_at <= decision_cutoff` 选择当时已经进入系统的数据。Market Outcome 只能作为运行完成后的 Observation 加入，不能回流到历史研究输入。

### 10. Eval 分层且包含 Agent 消融

评估分为：

1. Schema、数学和硬约束的确定性测试。
2. 来源完整率、freshness、冲突检测和引用支持度。
3. Thesis、反证、冲突处理、失效条件和置信度校准。
4. 多期限相对收益、回撤、换手、暴露、成本和 Thesis 事件实现。
5. CIO 单体、不同 Agent 组合和完整 Council 的消融比较。

晋升评估必须使用固定版本和留出集。市场收益不能作为唯一正确性标签，也不得通过反复调整同一历史区间选择表现最好的 prompt。

### 11. 学习循环只产出提案

Decision Trace、分类 Human Feedback 和多期限 Market Outcome 进入离线 Attribution Dataset。Reflection 可以生成 Improvement Proposal，包含失败模式、证据、根因假设、拟修改对象、预期收益、退化风险、Replay 计划和回滚条件。

Improvement Proposal 无生产写权限。开发控制面根据它创建新的 OpenSpec Change 或候选版本，经过 Regression、对抗样本、人工评审和 Shadow Run 后手工晋升。

### 12. 分阶段交付纵向切片

实现不按目录横向铺开，而按可运行能力纵向推进：

1. 三平面治理和核心 Schema。
2. point-in-time Evidence 与只读数据契约。
3. 持仓规范化和 Risk Kernel。
4. Company Research 完整 Capability。
5. CIO + Company Analyst + Risk Engine 的首个端到端切片。
6. Skeptic 和 Market/Catalyst 扩展。
7. Decision Trace、Replay、Eval 和学习提案。

实际 Codex Package manifest 在第一个端到端切片出现时创建，避免先生成空 Agent 包。

## Risks / Trade-offs

- [多 Agent 产生重复研究、成本和延迟] -> 使用动态委派、预算上限、并行执行和 Agent 消融门禁。
- [Agent 通过共享上下文相互锚定] -> 第一轮隔离研究，结构化 Artifact 汇总，第二轮才做定向反证。
- [数据源修订导致历史回放失真] -> Evidence Store 保存 `as_of`、`retrieved_at`、内容哈希和所有版本。
- [MCP 把外部评分伪装成系统判断] -> MCP 仅返回带来源定义的事实和确定性计算，任何第三方评分都标记为外部事实。
- [Risk Engine 逐渐演变成投资规则引擎] -> 每条规则必须映射到数学定义、数据质量或明确 Mandate，并接受架构评审。
- [模型自评形成闭环偏差] -> 关键样本采用人工评审或独立 grader，并保留确定性指标与反例。
- [市场结果噪声诱导错误优化] -> 使用多期限、基准、风险、成本和 Thesis 事件分解，不以单次涨跌标记对错。
- [长期存储完整工具输出带来成本] -> 保存规范化 Evidence、内容哈希和可重取定位；对受许可约束的数据采用受控快照策略。
- [用户把 advisory plan 当成交易指令] -> 所有输出固定标记 `advisory_only`，产品包完全不包含交易写工具。

## Migration Plan

该项目目前没有现有运行系统，采用增量启用而非数据迁移：

1. 先建立治理、Schema 和只读权限测试；默认不启用 portfolio council。
2. 建立 provider-neutral MCP 契约、fixture/reference adapter 和 Evidence Store，使用固定样本验证 point-in-time 语义。
3. 启用持仓规范化、Risk Kernel 和 Company Research 离线流程。
4. 在历史或合成持仓上启用首个 Council 纵向切片，只输出 `advisory_only` 结果。
5. 通过 Eval 后增加 Skeptic 与 Market/Catalyst，并继续保持 shadow 使用。
6. 最后启用反馈、Outcome 和 Improvement Proposal 流程。

任何阶段回滚均通过恢复上一套已批准的版本清单完成；Evidence 和 Decision Trace 保持追加式，不随回滚删除。

## Open Questions

以下问题明确留给后续部署或数据适配 Change，不属于本 Change 的实现与验收范围，因此不改变当前任务分解：

- 首发单一市场选择 A 股、港股或美股。
- 首批生产数据供应商及其许可、修订历史和 point-in-time 能力。
- 某个实际部署 Mandate 的仓位、行业、流动性和换手阈值数值。
