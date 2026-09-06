# Context

当前 0.1.0 已具备 Evidence、结构化报告、确定性 Risk Engine、Decision Trace 与 Eval 的基础契约，但端到端参考链路仍由 Python callback 模拟多个角色，尚不能证明 `portfolio-council` Skill、独立 Subagents 与真实 LLM 实际参与了投资委员会推理。

本 Change 在不接入真实市场数据的前提下，将 fixture 纵向链路激活为 Codex-native 运行模式。Codex 主线程承担 CIO 职责，显式委派 Company Analyst 与 Independent Skeptic 两个隔离的专业 Agent；Python 继续只负责 fixture 读取、时间点过滤、Schema 校验、哈希、数学计算、硬风控和产物持久化。

该设计同时跨越产品入口、Agent/Skill 配置、Evidence Gate、Risk Engine、Trace、Replay 和 Eval，因此需要统一设计约束，避免各组件分别实现后形成第二套 Python LLM 编排后端。

设计审视时，本机 `codex-cli 0.153.4` 已确认 `multi_agent` 为 stable，`codex exec` 支持显式模型、JSONL 事件、输出 Schema、严格配置和工作目录参数，并已通过真实探针验证项目级自定义 Agent 委派。实现不得假设这些能力等同于“模型实际关注了某段 Skill 内容”；验收只能证明仓库指令被解析并纳入调用包、相应 Agent 调用发生，以及输出遵循 Skill 专属协议。

# Goals / Non-Goals

## Goals

- 以 `portfolio-council` Skill 作为唯一产品入口，通过 Codex 原生能力调用真实 LLM 和独立 Subagents。
- 通过 fixture-only、Gate-scoped 只读 MCP 向 Agent 提供证据和确定性计算，并记录真实工具调用。
- 固定执行 Company Analyst 与 Independent Skeptic 两个并行、相互隔离的研究任务，再由当前 Codex 主线程以 CIO 身份综合。
- 在任何研究上下文构建前执行 point-in-time Evidence Gate，禁止未来事实、未来抓取记录和不满足新鲜度要求的数据进入 Agent 输入。
- 在专业报告、CIO 草案、Risk Engine 结果和最终输出各边界执行结构化校验与 Evidence 引用闭包校验。
- 生成可审计、可重放的 `decision.json`、`report.md` 和 `decision_trace.json`，并保存实际 Agent、Skill、Prompt、模型、数据和 Risk Engine 版本信息。
- 使用四类 fixture 完成可执行验收，并至少保留一次真实 Codex LLM 运行的完整、无敏感信息产物。
- 区分正常完成、安全 NO_TRADE 与系统校验失败，避免用 NO_TRADE 掩盖错误。

## Non-Goals

- 不接入真实行情、SEC、FRED、期权或其他外部市场数据 Provider。
- 不支持多市场、动态 Agent 路由或按问题自动扩充 Agent 队伍。
- 不提供自动下单、经纪账户写操作或任何真实交易能力。
- 不实现 Reflection Agent、自我修改或自动版本晋升。
- 不构建独立的 Python LLM 服务、对话循环或 Agent 编排后端。
- 不要求 LLM 文本在重复运行时逐字节一致。

# Decisions

## 1. Codex 主线程是 CIO，Skill 是产品入口

`portfolio-council` Skill 负责声明完整工作流、输入输出契约、委派顺序和失败策略。用户从 Codex 调用该 Skill；当前主线程在加载 CIO 指令后承担 CIO 身份，并通过 Codex 原生 Subagent 能力显式委派 Company Analyst 与 Independent Skeptic。

为 CIO、Company Analyst 和 Independent Skeptic 分别维护独立、带版本的 Agent 定义。CIO 即使由主线程执行，也必须有可哈希、可追踪的独立 Agent 指令，不能只依赖根 `AGENTS.md` 中的开发规则。

Smoke 启动前执行仓库资源发现预检，解析 `product` 包中的 Plugin manifest、`portfolio-council` Skill、CIO 指令和两个 runtime Agent 定义，并把规范化绝对路径、版本与内容 hash 写入 run manifest。若解析到了用户全局同名 Skill/Agent、资源缺失或内容与候选 manifest 不一致，运行在调用 LLM 前失败。具体激活方式可以随 Codex CLI 版本采用仓库工作目录、repo-local 配置或可审计的本地 Plugin 安装，但验收语义保持一致。

Python 可以由 Skill 或 Agent 调用来完成确定性步骤，但不得调用 LLM、模拟多个 Agent、决定主观投资观点或控制对话循环。

备选方案是新增 Python orchestrator 调用模型 API；该方案会形成独立应用运行面，绕过 Codex Skill/Subagent 生命周期，故拒绝。

## 2. 本 Change 使用固定双 Agent 拓扑

每次可交易研究运行固定委派以下两个 Agent：

1. Company Analyst：形成公司研究 Thesis、关键证据、风险、失效条件和建议倾向。
2. Independent Skeptic：独立寻找反证、证据缺口、冲突、替代解释和 NO_TRADE 理由。

两者获得同一份经过过滤的 Evidence 集合和同一份持仓上下文，但使用独立上下文并并行执行。Skeptic 的输入在派发前生成并哈希，禁止包含 Analyst 输出、摘要或派生结论。只有 CIO 可以同时读取两份结构化报告。

“并行”定义为两个委派请求都在父线程等待任一结果之前发出；不要求两个模型调用具有完全重叠的墙钟时间。这样既可通过 Codex 事件验证，又不把调度器实现细节误写成投资协议。

现有规范中的“动态委派”在本 Change 中收敛为固定 profile；动态路由留待后续 Change，避免在尚未证明单一纵向链路时提前增加空 Agent 和路由复杂度。

## 3. Evidence Gate 在 Agent 派发前 fail closed，但不替代投资判断

Evidence Gate 是确定性前置关卡，输入为原始 fixture、`decision_cutoff`、新鲜度策略和 Schema 版本，输出为不可变的 filtered evidence artifact 与排除记录。

确定性 Gate 只处理可机械判断的条件。允许进入 Agent 工具面的事实必须同时满足：

- `retrieved_at <= decision_cutoff`
- `as_of <= decision_cutoff`
- 必填来源字段完整，包括 `evidence_id`、`source_id`、`as_of` 和 `retrieved_at`
- 符合该数据类型明确声明的新鲜度策略

Gate 记录每条被排除事实的原因，包括 future-as-of、future-retrieval、stale、missing-metadata 和 invalid-schema。对于同一规范化 conflict key 的不兼容值，Gate 保留全部通过时间门禁的来源并标记冲突，不判断哪一方可信，也不判断冲突是否足以改变投资动作。

若 Gate 后没有任何可用事实，或 portfolio 输入无法通过确定性契约，运行可以在 Agent 前形成 `SAFE_NO_TRADE`。只要仍有可用事实，证据是否足够、缺口或冲突是否实质以及是否应当 NO_TRADE 都由专业 Agent 与 CIO 判断。该分工防止 Python freshness/coverage 逻辑演化成投资评分规则。

Agent 只能按 `evidence_id` 引用 Gate 允许集合中的事实。专业报告、CIO 草案和最终决策均执行引用闭包校验；悬空引用或引用被过滤事实时进入 `FAILED_VALIDATION`，不得转成 NO_TRADE 或只在 Markdown 报告中警告。

## 4. 结构化产物和 Gate-scoped MCP 是唯一交接面

Company Analyst 与 Independent Skeptic 的 Invocation Manifest 只携带 portfolio 上下文、研究范围、cutoff、允许 Evidence IDs、只读 MCP capability 和版本信息。事实内容通过绑定 `run_id` 的 fixture MCP 查询；MCP adapter 只服务 Gate 允许集合，拒绝未知、被排除或跨 run ID 的查询，并且不提供原始 fixture 文件、外部网络或写能力。

两个 Agent 只能输出各自版本化 Schema 的专业报告。CIO 只接收：

- 经过 Evidence Gate 的允许 Evidence References 和同一只读 MCP 查询能力
- 两份已通过 Schema 和引用闭包校验的专业报告
- 组合与风险政策所需的确定性数据

CIO 不接收 Subagent 的隐藏推理过程，也不依赖聊天历史中的非结构化结论。CIO 输出结构化 decision draft，再交由 deterministic Risk Engine 校验、调整或否决。

Agent 返回结构有效的 `INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE` 或 `TIMEOUT` 是领域状态，可由 CIO 综合成 `SAFE_NO_TRADE`。非法 JSON、Schema 不符、悬空引用、跨 run 取证或伪造执行元数据是系统错误；在一次仅限格式的受控修复仍失败后，运行进入 `FAILED_VALIDATION`。

Risk Engine 只执行明确、可测试的硬约束，例如仓位、集中度、现金、可交易性和组合核算约束；不得把“公司是否优秀”“估值是否合理”等投资判断编码成大型 if/else 规则。

## 5. 运行目录保存完整、分层的审计包

每次运行使用唯一 `run_id`，建议产物布局如下：

```text
runs/<run_id>/
├── manifest.json
├── input/
│   └── portfolio.json
├── evidence/
│   └── gate.json
├── invocations/
│   ├── company_analyst.json
│   ├── independent_skeptic.json
│   └── cio.json
├── runtime/
│   └── codex_events.jsonl
├── agents/
│   ├── company_analyst.json
│   └── independent_skeptic.json
├── cio/
│   └── decision_draft.json
├── risk/
│   └── risk_result.json
├── eval/
│   └── eval_result.json
├── decision.json
├── report.md
├── decision_trace.json
└── run_error.json
```

fixture、正式验收证据和临时运行输出应分开管理。临时运行目录默认不作为产品源码提交；至少一次真实 LLM 验收运行需将经过敏感信息检查的 manifest、Invocation Manifests、最小化 Codex JSONL 事件、结构化产物、Trace、Eval 结果和实际命令保存到版本化验收目录。

上图列出所有可能产物，并非每个终态都同时存在：

- `COMPLETED`：保存三个最终文件以及所有中间审计产物。
- `SAFE_NO_TRADE`：同样保存三个最终文件；若在 Gate 前置阶段终止，Agent/CIO 目录可以为空，但 Trace 必须说明未调用原因。
- `FAILED_VALIDATION`：保存 `decision_trace.json`、`run_error.json` 和失败前已产生的审计产物，不保存 `decision.json` 或 `report.md`。

`report.md` 由已验证的结构化数据确定性渲染，不得引入 `decision.json` 中不存在的新事实、新引用或新交易动作。

## 6. Trace 记录执行证明，不夸大可观测性

每个 Agent 执行节点在调用前生成 Invocation Manifest，并记录：

- `run_id`
- Agent name、role、version、解析路径与定义文件 hash
- 纳入仓库可控 instruction bundle 的 Skill name、version 与内容 hash
- task prompt template identifier/hash 与完整 repo-controlled instruction bundle hash
- Smoke 显式指定的 model identifier 和 Codex runtime version
- 输入 Evidence IDs
- 规范化 input hash 与 output hash
- 开始/结束时间、状态和验证结果

Trace 还必须关联最小化的 Codex JSONL Agent 调用事件、fixture MCP 工具事件、Evidence Gate 输入输出 hash、数据/Schema/适配器版本，以及 Risk Engine 的 policy version、原始 CIO 动作、每次修改、最终动作和否决原因。

三项证据共同构成 Agent/Skill 参与证明：Invocation Manifest 证明仓库指令被解析并纳入调用包，Codex 事件证明对应 Agent 调用真实发生，结构化输出与工具关联证明 Skill 专属协议被执行。Agent 自报 Skill 名称不能单独作为证据。系统不声称能证明模型对指令的内部注意力，也不尝试保存 OpenAI 内部系统指令或隐藏 chain-of-thought。真实验收必需字段缺失时验收失败，禁止用 placeholder 填充。

## 7. Replay 分为精确重建与 LLM 再运行

Replay 提供两个层次：

- Artifact replay：基于已保存的 Agent 输出、Evidence、版本和 Risk policy，重新执行校验、Risk Engine、Trace 关联和 Markdown 渲染；其结构化结果必须确定性一致。
- Native rerun：使用相同 fixture、cutoff、Agent/Skill/Prompt/Schema 版本和指定模型重新调用 Codex。由于 LLM 非确定性，不要求自然语言逐字一致，但必须通过 Schema、Evidence closure、风险约束和语义 Eval。

这一区分既保证可审计性，也避免用不现实的字节级 LLM 重现要求掩盖真正的契约回归。

## 8. Smoke 通过 Codex 非交互入口执行

仓库提供一条可复制的 `codex exec` 或当前 Codex 版本等价命令，用 fixture 路径、cutoff、显式模型和全新输出目录启动 `portfolio-council` Skill。该命令启用机器可读事件和严格配置检查，并首先证明解析的是仓库产品包。实现时以本机已安装 Codex 的帮助信息验证精确参数，把实际命令与 Codex 版本写入验收 manifest。

Smoke 禁用实时 Web、真实 Provider 和用户全局同名 Agent/Skill 依赖，只启用 fixture MCP 与确定性工具。运行前后对产品代码、Agent、Skill、Schema 和 Risk Policy 计算完整性 hash；若运行过程修改任一受保护文件，验收失败。输出只写到显式运行目录，正式验收建议在隔离工作区执行。

允许提供小型 Python 确定性命令用于 fixture 校验、Evidence Gate、Risk Engine、Schema 检查、哈希、Replay 和存储，但 Smoke 的 LLM 编排入口必须是 Codex，而不是 `python3 -m product`。

## 9. 验收采用四个场景和真实调用证据

至少提供以下 fixture：

- 正常研究：证据完整、时间有效，形成可审计建议或基于研究判断的 NO_TRADE。
- 未来或过期数据：证明 Gate 在 Agent 调用前过滤，并在证据不足时 NO_TRADE。
- Analyst/Skeptic 证据冲突：证明独立报告都保留、CIO 显式处理冲突与失效条件。
- Risk Engine 否决：证明 CIO 草案可被确定性策略修改或否决，最终动作与 Trace 一致。

单元测试可使用 fake adapter 验证边界，但不能作为 Change 验收中的真实 LLM 证据。验收至少执行一次真实 Codex LLM 正常运行，并保存显式模型、Invocation Manifests、Agent/Skill/task prompt hashes、Codex 与 MCP 事件、完整产物、Eval 结果、执行命令和退出状态。若模型不可用、配额不足或真实性元数据缺失，Change 保持未完成，而不是退回 mock-only 后宣称通过。

Risk veto 场景采用双重证据，避免把 LLM 动作硬编码进 fixture：

1. 每个产生 CIO draft 的真实 native 运行都必须经过同一 deterministic Risk Engine，Trace 保存实际结果。
2. 额外的 Risk boundary fixture 使用明确标记为测试输入的固定 draft，稳定触发 `REVISE_REQUIRED` 或 `REJECTED`，证明相同 policy version 可重复修改或否决。该 draft 的 producer 必须是 fixture，不能冒充 CIO LLM，也不能满足真实 LLM 门禁。

四类 fixture 的自动 Eval 只检查结构化不变量。正常场景不预设 BUY/HOLD 等动作；未来/过期场景检查精确过滤与安全终态；冲突场景检查双方来源、独立反证和 CIO 显式消费；Risk 场景检查真实风险经过与确定性 boundary veto。MVP 不从四个 fixture 推断市场收益、Alpha 或统计显著的预测提升，多 Agent 增益只验证 Skeptic 提供了非重复信息并实际影响 CIO 的冲突记录或不确定性表达。

# Risks / Trade-offs

- **Codex 版本和运行环境差异**：不同版本的 Agent、Skill 和非交互参数可能不同。实现时增加资源发现与能力探测，记录实际 Codex 版本，Smoke 文档只采用已验证命令。
- **LLM 输出非确定性**：对结构、引用、风险与关键语义做确定性和 rubric Eval；不以整段文本 golden snapshot 作为主要门禁。
- **Subagent 信息泄漏**：在并行派发前生成并哈希两个输入包，禁止在 Skeptic 输入中出现 Analyst 输出 hash 或内容，Eval 验证隔离性。
- **无法证明模型内部注意力**：用 Invocation Manifest、Codex 调用事件和 Skill 专属输出/工具关联证明可观测的参与范围，并明确不作内部注意力声明。
- **Trace 误收集敏感或隐藏推理**：只记录显式输入、输出、标识、时间和 hash，不记录隐藏 chain-of-thought。
- **真实 LLM 验收受配额或网络影响**：失败必须明确暴露并阻断晋升；fake adapter 仍用于快速单元测试，但不能替代真实验收。
- **LLM 可能输出无效引用**：每个交接边界 fail closed；一次受控的格式修复可以作为同一 Agent 的验证重试，但不得添加新事实或绕过 closure。
- **Python 边界再次膨胀**：增加架构测试和 review checklist，禁止运行时 Python 模块导入模型 SDK、形成角色 prompt 或决定 thesis/action/confidence。
- **Risk veto 场景受 LLM 自主动作影响**：同时保存真实 Council 的风险经过和确定性 boundary veto，后者不冒充 LLM 输出。
- **运行时修改产品文件**：在隔离工作区运行 Smoke，并对受保护产品文件执行前后完整性校验。

# Migration Plan

1. 保留 0.1.0 callback/reference 流程作为测试参考，但明确标记为 test-only，禁止被 Codex-native 产品入口调用。
2. 新增候选运行 profile、Agent 定义、Skill 工作流、fixture 和版本化 Schema，不立即替换已归档基线。
3. 先通过确定性单元测试、fixture MCP 契约、终态和 Risk boundary fixture 验收，再执行四场景 Smoke 与至少一次真实 Codex LLM 正常运行并保存验收包。
4. 完成 OpenSpec 校验、架构边界审查、Replay/Eval 和人工审批后，才更新生产版本指针。
5. 若真实运行失败或回归，则恢复到既有 0.1.0 版本指针；已保存的候选运行产物仅用于诊断，不触发任何外部交易行为。

# Resolved Implementation Constraints

- 规范不指定全局默认模型。普通运行可继承调用者配置，但正式 Smoke 必须通过已验证命令显式指定模型；Trace 记录该调用参数和实际 Codex runtime。无法可靠确定模型时验收失败。
- 真实 LLM 验收包保存到版本化的 Eval 运行目录，提交完整结构化输入输出、Invocation Manifests、最小化 Codex 事件、Trace、Eval、命令、Codex 版本和退出状态；不提交包含环境噪声或潜在敏感信息的完整原始终端日志。提交前执行敏感信息检查。
