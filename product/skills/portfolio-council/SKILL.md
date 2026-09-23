---
name: portfolio-council
description: 用户提供已确认 PortfolioHandoff 并调用投资委员会时，主持普通股持仓研究或多维研究阶段；fixture 兼容链路可完成专业研究、CIO 综合和确定性风险校验；不用于开发任务。
metadata:
  version: "3.5.0"
---

# Portfolio Council

本 Skill 是 Council 的唯一产品入口。已确认 `PortfolioHandoff v3` 是当前用户持仓入口；旧 `live-us-equity` 完整 Council 宿主入口已退役。当进入 fixture 完整 Council 兼容链路时，Codex 主线程担任 CIO。Python 只执行数据获取与标准化、确定性预检、Evidence Gate、数学计算、Schema/引用校验、Risk Engine、哈希、渲染与存储，不得生成 Thesis、动作或置信度。

## 普通股持仓研究阶段

当用户提供已确认的完整 `PortfolioHandoff v3` 并要求分析普通股持仓时，本 Skill 选择 `stage=COMMON_STOCK_RESEARCH`；主线程只担任研究调度者，不担任 CIO。系统自动构造绑定的 `CouncilRequest`，通过宿主入口复用现有只读适配器或合格缓存准备并冻结公司资料，用户不需要转换文件或制作 Evidence/Gate。

主线程先保留全部持仓规划，再只为 `company-research=AVAILABLE` 的普通股创建独立 `HoldingResearchRequest`。默认最多同时派发三个 `runtime_company_analyst`，持仓数量不设上限；在等待首项结果前先填满可用槽位，后续按空位补充。每个调用只接收一只证券、允许的 Evidence IDs 和自身输出 Schema，不接收成本、浮亏、现金、其他持仓或其他 Agent 结论。

Company Analyst 必须实际使用 `evidence-grounding`、`company-research`、`valuation` 和公司级 `catalyst-analysis`，输出 `EquityResearchReport` 研究草案；运行层只封装技术绑定和 hash，不修复研究内容或 Evidence 引用。报告通过 Schema、PIT 与 Evidence Closure 后生成逐证券 `equity-research.json` 和中文 `equity-research.md`。合法缺口可以保留，但不自动等于研究质量通过。

研究模型可在该批次显式指定，未指定时使用现有 `runtime_repeated` 路由；不支持的模型必须在启动前拒绝，禁止静默回退。批次父运行模型与 Company Analyst 实际模型分别记录；聚焦 Eval 使用独立评分模型配置，普通产品研究不会隐式启动 Eval。

本阶段停止于普通股报告集，不启动 Skeptic、CIO、Risk，不生成完整组合 `decision.json`。ETF、期权及失败证券必须留在 `ResearchCoverage` 中并明确标记 `CAPABILITY_GAP`、`NOT_RESEARCHED` 或失败；即使全部输入都是普通股，也不能把本阶段称为完整 Council 或完整组合建议。fixture 完整 Council 兼容路径继续执行下述固定阶段，不受此分支放宽。

## 多维持仓研究阶段

当用户要求在进入反证和组合决策前补全免费公开资料研究时，本 Skill 显式选择 `stage=MULTI_DIMENSIONAL_HOLDING_RESEARCH`。该阶段承接同一份确认 Handoff，只研究普通股，并保留 ETF、期权和账户项的未覆盖状态；用户不需要自行准备 Evidence。

在正式研究前先执行 `MULTIDIMENSIONAL_MATERIAL_PREPARATION`：Company Analyst 可在绑定的准备 invocation 中调用 `research_search` / `research_fetch` 自动寻找并取得公开正文；Market Catalyst 只从冻结 NASDAQ 候选池选择有理由的同行候选。搜索线索不是正文，同行候选不是事实。正文和实际选择的同行资料由确定性工具冻结并重新通过 PIT Gate，随后正式 invocation 才能读取；正式 invocation 不继承搜索权限。正文 API key 缺失等配置问题为 `BLOCKED_CONFIGURATION`，真实来源路径受限为 `SOURCE_LIMITED`，两者均须引用实际工具尝试产物。

主线程只负责依赖调度与产物归集，不担任 CIO。`runtime_company_analyst` 负责基本面深化、公司事件及公司研报；`runtime_market_catalyst` 按隔离 invocation 负责技术结构、行业、宏观市场、所有权披露、期权/资金结构及行业研报。每次 invocation 只执行一个 capability；共享宏观任务只运行一次。具备合格输入的独立任务在三槽内有界并行，同行比较等待身份和资料核实，研报正式分析等待正文冻结及 PIT Gate。单项失败只阻塞其真实依赖项，每个已验证报告立即展示路径和进度。

所有新维度返回 `ResearchDimensionReport`；最终只组装 `HoldingResearchBundle` 及同源中文报告。报告不得包含 `action`、目标权重、推荐数量或订单。最终包必须区分 `STRUCTURALLY_CONSUMABLE` 与 `DOWNSTREAM_READY`；后者要求兼容的逐股 `EquityResearchReport` 已纳入，且补证来源、Evidence closure 及待反证问题完整。不同 run、cutoff 或 CouncilRequest 的报告不得静默拼接。不同维度的观察与失效条件按原报告引用归集为 `unresolved_cross_dimension_questions`，拼接程序不得代替后续 Skeptic/CIO 解决。本阶段明确停止在研究包，不启动 Skeptic、CIO 或 Risk。

## 正向研究与独立反证阶段

仅当用户明确要求正向多维研究后继续独立反证时，选择 `stage=INDEPENDENT_COUNTER_THESIS_RESEARCH`。在一个新冻结运行中复用上述资料准备、多维正向研究与 `HoldingResearchBundle`；本次 bundle 必须通过 Schema、run/cutoff/Gate/Request 绑定、Evidence Closure、`DOWNSTREAM_READY` 及核心 Company、Technical、Fundamental/Event、Industry、Macro、Market 覆盖门禁后，才启动逐普通股 `runtime_skeptic`。原多维阶段仍停于正向包，不自动补写反证。

每只普通股独立派发 `INDEPENDENT_FIRST_PASS`，使用不继承父会话的上下文与只读 Gate-scoped 查询。输入由原始 Gate 和非结论性请求单独构造，不读取正向报告、bundle 正文、摘要、未解决问题或其 hash；服务端按逐 Invocation 允许集合拒绝其他持仓资料。原始报告和中文正文逐股保存。合法 `COMPLETE` 或已完成研究的 `LOW_CONFIDENCE` 可使交接包达到 `DOWNSTREAM_READY`；`INSUFFICIENT_EVIDENCE`、`TIMEOUT` 和系统失败只保留部分交接。`DOWNSTREAM_READY` 仅表示结构与执行可供后续研究消费，不代表研究质量、投资建议或 Eval 通过。

本阶段只输出正向包、逐股 Counter Thesis、`PreDecisionResearchPackage` 和同源中文摘要；不启动 CIO、Risk，不生成 `decision.json`、动作、Outcome 或回测。ETF、期权及账户项的未覆盖状态继续展示。

## 必要输入

- 持仓研究：已确认的 `PortfolioHandoff v3`；系统从中派生内部普通股采集请求，冻结 snapshot、Gate 和 data-preparation manifest。
- fixture 完整 Council：仓库内版本化 `portfolio_fixture`。旧 live profile 及三股 batch 入口不再是产品入口。
- `decision_cutoff`、显式 `model`、全新的 `output_dir` 和用户研究目标。
- 可选的 Mandate 只能收紧建议边界，不得授权真实交易。

先执行仓库产品包 discovery preflight，锁定 Plugin、此 Skill、`runtime_cio`、`runtime_company_analyst`、`runtime_skeptic`、canonical decision contract、Schema、fixture adapter、Risk policy 和数据快照的规范化路径、版本及 hash。任何资源缺失、解析到仓库外同名资源、版本或 hash 不一致，均在 LLM 调用前进入 `FAILED_VALIDATION`。

## 固定运行阶段

以下固定双专业 Agent、CIO 和 Risk 流程当前仅用于 fixture 完整 Council 兼容链路。真实数据持仓链路按上述显式研究阶段停止，不得因底层兼容函数存在而启动旧完整 Council。

1. 创建唯一 `run_id` 和显式运行目录，保存输入及候选版本 manifest；禁止覆盖已有目录。
2. 确定性校验 fixture portfolio 输入，并在任何 Agent 获取上下文前执行 point-in-time Evidence Gate。Gate 排除 `as_of` 或 `retrieved_at` 晚于 `decision_cutoff` 的事实，应用版本化 freshness policy，机械标记规范化字段冲突，保存允许/排除 Evidence IDs 与 bundle hash，并生成内容寻址 Replay Capsule。真实数据的 `published_at`、财报期间、交易日历和 source context 校验在前述数据准备阶段完成。
3. 仅当输入有效且 Gate 仍有可用证据时继续。为两个专业 Agent 生成不可变 Invocation Manifest 和相互独立的输入包。
4. 在等待任一结果前，通过 Codex 原生委派能力同时启动 `runtime_company_analyst` 与 `runtime_skeptic`。两个 Agent 必须使用独立会话与隔离上下文；Skeptic 第一轮不得接收 Analyst/CIO 输出、摘要、hash 或派生结论。默认不得调用所有 runtime Agent；本 Profile 只调用固定双 Agent，不调用 Market/Catalyst 或其他 Agent。
5. Agent 只能通过绑定本次 `run_id`、invocation 和 source mode 的 `fixture_evidence.query` 读取 Gate 允许事实；Company Analyst 可额外调用只读确定性计算工具。禁止读取原始 fixture、被排除事实、实时 Web、外部 Provider、App、券商、账户和任何写工具。
6. 对两份报告分别执行结构和 Evidence Closure 校验。纯格式错误最多允许原 Agent 修复一次，且不可新增事实或扩大 Evidence 集合。合法的 `INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE`、`TIMEOUT` 是领域状态；非法 JSON、Schema、引用、身份或执行元数据是系统错误。
7. CIO 只接收已验证的结构化专业报告、Evidence References、确定性组合数据和 Gate-scoped 核验工具。综合共识、冲突、未解决问题、Thesis、Counter Thesis、置信度理由和可观察失效条件；允许选择 `NO_TRADE`，但必须遵守 Invocation task prompt 中由 canonical decision contract 生成的条件与示例，不得使用预写结论。
8. 每个可形成的 CIO draft 必须进入 deterministic Risk Engine。禁止覆盖 `REJECTED`；`REVISE_REQUIRED` 最多修订一次，第二次仍未通过时移除违规意图或形成 `NO_TRADE: RISK_VETO`。
9. 在 CIO draft、Risk result 和最终决策边界再次执行 Schema 与 Evidence Closure 校验，由确定性渲染器生成产物并运行实际 Eval。

## Replay 与评估拓扑

- Artifact Replay 只验证冻结运行包，不调用 LLM，也不改写源 Run。
- Execution Replay 必须从已验证 Replay Capsule 在隔离工作区创建新的 `run_id`，重新运行本 Skill、独立 Agent、CIO 和 Risk；不得从当前仓库或全局同名 Skill 补齐缺失资源。
- 只有开发控制面明确标记为 `EVAL_ABLATION` 时，才允许 `cio-only`、`analyst-cio` 或 `full-council` 实验拓扑。A/B 结果是不可发布评估产物，不能冒充默认产品建议；所有形成的 CIO 草案仍必须经过 Risk Engine。

## 三类互斥终态

- `COMPLETED`：LLM Council 与 Risk Engine 均完成，保存 `decision.json`、`report.md`、`decision_trace.json` 及全部审计产物。
- `SAFE_NO_TRADE`：portfolio 输入无效、Gate 后无可用事实，或 CIO 作出结构有效的 NO_TRADE；同样保存三个终态文件。前置安全终止时不得出现 Agent 调用事件。
- `FAILED_VALIDATION`：资源、执行证明、Schema、Evidence Closure、跨 run、完整性或持久化校验失败；只保存带一致 `failed_stage` 的 `decision_trace.json`、`run_error.json` 和失败前审计产物，禁止生成 `decision.json` 或 `report.md`。Risk 前失败允许空 Risk lineage，进入 Risk 后必须保存完整尝试和结果血缘。

只要 fixture portfolio 输入有效且 Gate 仍有可用证据，Python 不得判断投资证据是否“足够”，必须执行固定双 Agent 委派。数据不足、过期或冲突是否具有投资实质性，由 LLM 报告与 CIO 综合判断。真实数据持仓研究按前述显式阶段和自身输出契约执行。

## 输出与执行证明

所有事实必须携带 `evidence_id`、`source_id`、`as_of`、`retrieved_at`。任何 `evidence_id` 都必须属于本次 Gate 允许集合；悬空、被排除或跨 run 引用直接导致 `FAILED_VALIDATION`。

Trace 必须关联 `run_id`、Agent/Skill 名称与版本、仓库路径与内容 hash、task prompt/instruction bundle hash、显式模型、Codex runtime、Invocation Manifest、独立会话标识、最小化 Codex JSONL 事件、MCP 工具事件、Evidence/Data/Schema/Policy 版本、输入输出 hash 以及 Risk Engine 的原始动作、修改、违规和否决。执行证明只表示协议被加载、调用和产物被验证，不声称模型注意力或隐藏思维链。

## 硬边界

- 全部结果仅供研究参考，始终声明 `advisory_only: true`。
- 禁止创建、路由、修改或取消订单；禁止索取凭据或修改账户。
- 运行期间禁止修改代码、Skill、Agent、Schema、Risk Policy、测试或版本指针。
- 禁止把投资判断编码成确定性评分或大型 if/else 规则。
- 禁止用 fake adapter、callback、固定字符串或 fixture 预期结果冒充真实 LLM 验收。
- 禁止将 `EVAL_ABLATION` 产物作为产品建议或正常 Release 候选；默认产品链路始终要求 Company Analyst 与 Independent Skeptic。
- fixture 完整 Council 的 `codex exec` 结束后必须独立运行确定性 `check-run`。普通股或多维研究阶段的结构可消费不代表研究质量、Change 验收或候选版本晋升通过。
- fixture 不访问真实来源；普通股持仓研究只消费采集层已准入并冻结的行情、证券目录与 SEC Evidence，不在 Agent 内重新联网。多维阶段只允许显式资料准备 invocation 使用绑定的只读来源工具，正式分析仍只消费 Gate 合格资料。禁止动态 Agent 路由、Reflection Agent 或任何写入型外部能力。
