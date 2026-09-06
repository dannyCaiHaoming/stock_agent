---
name: portfolio-council
description: 当用户提供版本化 portfolio fixture 并请求运行 Codex-native 投资委员会时，主持只读、仅供建议的双 Agent 研究、CIO 综合和确定性风险校验闭环。
metadata:
  version: "2.0.0"
---

# Portfolio Council（Fixture Council 2.0）

本 Skill 是 fixture Council 的唯一产品入口。当前 Codex 主线程担任 CIO；Python 只执行确定性预检、Evidence Gate、数学计算、Schema/引用校验、Risk Engine、哈希、渲染与存储，不得调用 LLM、生成 Thesis、动作或置信度。

## 必要输入

- 仓库内版本化 `portfolio_fixture` 路径。
- `decision_cutoff`、显式 `model`、全新的 `output_dir` 和用户研究目标。
- 可选的 Mandate 只能收紧建议边界，不得授权真实交易。

先执行仓库产品包 discovery preflight，锁定 Plugin、此 Skill、`runtime_cio`、`runtime_company_analyst`、`runtime_skeptic`、Schema、fixture adapter、Risk policy 和数据快照的规范化路径、版本及 hash。任何资源缺失、解析到仓库外同名资源、版本或 hash 不一致，均在 LLM 调用前进入 `FAILED_VALIDATION`。

## 固定运行阶段

1. 创建唯一 `run_id` 和显式运行目录，保存输入及候选版本 manifest；禁止覆盖已有目录。
2. 确定性校验 portfolio fixture，并执行 point-in-time Evidence Gate。Gate 同时排除 `as_of` 或 `retrieved_at` 晚于 `decision_cutoff` 的事实，应用声明式 freshness policy，机械标记规范化字段冲突，并保存允许/排除 Evidence IDs 与 bundle hash。
3. 仅当输入有效且 Gate 仍有可用证据时继续。为两个专业 Agent 生成不可变 Invocation Manifest 和相互独立的输入包。
4. 在等待任一结果前，通过 Codex 原生委派能力同时启动 `runtime_company_analyst` 与 `runtime_skeptic`。两个 Agent 必须使用独立会话与隔离上下文；Skeptic 第一轮不得接收 Analyst/CIO 输出、摘要、hash 或派生结论。默认不得调用所有 runtime Agent；本 Profile 只调用固定双 Agent，不调用 Market/Catalyst 或其他 Agent。
5. Agent 只能通过绑定本次 `run_id` 的 `fixture_evidence.query` 读取 Gate 允许事实；Company Analyst 可额外调用只读确定性计算工具。禁止读取原始 fixture、被排除事实、实时 Web、外部 Provider、App、券商、账户和任何写工具。
6. 对两份报告分别执行结构和 Evidence Closure 校验。纯格式错误最多允许原 Agent 修复一次，且不可新增事实或扩大 Evidence 集合。合法的 `INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE`、`TIMEOUT` 是领域状态；非法 JSON、Schema、引用、身份或执行元数据是系统错误。
7. CIO 只接收已验证的结构化专业报告、Evidence References、确定性组合数据和 Gate-scoped 核验工具。综合共识、冲突、未解决问题、Thesis、Counter Thesis、置信度理由和可观察失效条件；允许选择 `NO_TRADE`，但不得使用预写结论。
8. 每个可形成的 CIO draft 必须进入 deterministic Risk Engine。禁止覆盖 `REJECTED`；`REVISE_REQUIRED` 最多修订一次，第二次仍未通过时移除违规意图或形成 `NO_TRADE: RISK_VETO`。
9. 在 CIO draft、Risk result 和最终决策边界再次执行 Schema 与 Evidence Closure 校验，由确定性渲染器生成产物并运行实际 Eval。

## 三类互斥终态

- `COMPLETED`：LLM Council 与 Risk Engine 均完成，保存 `decision.json`、`report.md`、`decision_trace.json` 及全部审计产物。
- `SAFE_NO_TRADE`：portfolio 输入无效、Gate 后无可用事实，或 CIO 作出结构有效的 NO_TRADE；同样保存三个终态文件。前置安全终止时不得出现 Agent 调用事件。
- `FAILED_VALIDATION`：资源、执行证明、Schema、Evidence Closure、跨 run、完整性或持久化校验失败；只保存 `decision_trace.json`、`run_error.json` 和失败前审计产物，禁止生成 `decision.json` 或 `report.md`。

只要 portfolio 输入有效且 Gate 仍有可用证据，Python 不得判断投资证据是否“足够”，必须执行固定双 Agent 委派。数据不足、过期或冲突是否具有投资实质性，由 LLM 报告与 CIO 综合判断。

## 输出与执行证明

所有事实必须携带 `evidence_id`、`source_id`、`as_of`、`retrieved_at`。任何 `evidence_id` 都必须属于本次 Gate 允许集合；悬空、被排除或跨 run 引用直接导致 `FAILED_VALIDATION`。

Trace 必须关联 `run_id`、Agent/Skill 名称与版本、仓库路径与内容 hash、task prompt/instruction bundle hash、显式模型、Codex runtime、Invocation Manifest、独立会话标识、最小化 Codex JSONL 事件、MCP 工具事件、Evidence/Data/Schema/Policy 版本、输入输出 hash 以及 Risk Engine 的原始动作、修改、违规和否决。执行证明只表示协议被加载、调用和产物被验证，不声称模型注意力或隐藏思维链。

## 硬边界

- 全部结果仅供研究参考，始终声明 `advisory_only: true`。
- 禁止创建、路由、修改或取消订单；禁止索取凭据或修改账户。
- 运行期间禁止修改代码、Skill、Agent、Schema、Risk Policy、测试或版本指针。
- 禁止把投资判断编码成确定性评分或大型 if/else 规则。
- 禁止用 fake adapter、callback、固定字符串或 fixture 预期结果冒充真实 LLM 验收。
- 本版本不接入真实行情、SEC/FRED、期权、多市场、动态 Agent 路由或 Reflection Agent。
