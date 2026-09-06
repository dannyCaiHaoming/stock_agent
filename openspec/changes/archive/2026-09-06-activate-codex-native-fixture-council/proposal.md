## Why

候选版本 `0.1.0` 已具备可执行的确定性契约、Evidence、Risk Engine、Trace 和 Eval 组件，但当前端到端路径仍由 Python 测试 callback 伪装专业 Agent 与 CIO，未实际加载 Codex Skill、未调用独立 LLM Subagents，并存在未来事实进入研究、最终 Evidence 悬空引用、Trace 无法关联真实 Prompt/Agent 调用等阻断问题。接入真实市场数据前，必须先用 fixture 证明 Codex-native 投资委员会能够真实运行、审计和复现。

## What Changes

- 将 `portfolio-council` Skill 激活为产品唯一入口，由当前 Codex 主线程担任 CIO，并通过独立 Agent 定义并行委派 Company Analyst 与 Independent Skeptic。
- 为该入口提供仓库内可发现性预检和 fixture-only 只读 MCP 工具面；专业 Agent 只能查询 Evidence Gate 允许的运行级证据集合，不得读取原始 fixture、访问外部市场数据或依赖用户全局同名 Skill/Agent。
- 以真实 Codex LLM 运行替代 Python callback 研究与硬编码 CIO 综合；禁止硬编码 Thesis、Action、Confidence，禁止用同一 callback 模拟多个 Agent。
- 在任何 Agent 研究前执行强制 point-in-time Evidence Gate，同时约束 `retrieved_at` 和 `as_of` 不晚于 `decision_cutoff`；确定性层只过滤时间、元数据、版本化 freshness 和可机械判定的规范化冲突，LLM 负责判断证据充分性、冲突实质性及其投资影响。
- 在 CIO 综合前校验专业报告 Schema 和 Evidence Closure，在最终输出前再次校验所有 Evidence References；数据不足或研究冲突可以形成合法 `NO_TRADE`，悬空引用、非法 Schema 或伪造运行元数据必须进入 `FAILED_VALIDATION`，不得伪装为投资性 `NO_TRADE`。
- 扩展 Decision Trace，使其记录真实 run、Codex 结构化执行事件、Agent、实际纳入调用指令包的 Skill、仓库可控 Prompt/Instructions、显式模型、输入输出、Evidence、工具调用、数据版本及 Risk Engine 修订和否决血缘；不声称记录或哈希 OpenAI 内部系统指令与隐藏推理。
- 提供 `decision.json`、`report.md` 和 `decision_trace.json` 三项稳定产物，以及可通过 `codex exec` 或等价 Codex-native 方式重复执行的 Smoke 命令。
- 明确运行终态：`COMPLETED` 与 `SAFE_NO_TRADE` 保存三个一致的最终产物；`FAILED_VALIDATION` 保存可审计 Trace 和结构化错误，但不得发布看似有效的最终建议。
- 建立正常研究、未来或过期数据、Analyst/Skeptic 证据冲突、Risk Engine 否决四类 fixture 验收；真实 Council 必须经过 Risk Engine，另以确定性 Risk boundary fixture 稳定证明修改和否决能力，且该固定 draft 不得冒充 LLM 投资结论。单元测试可使用 fake adapter，但 Change 完成必须保存至少一次真实 Codex LLM 运行的完整产物和实际 Eval 结果。
- 保持仅供建议、只读和不可下单边界；不增加独立 Python LLM 编排后端，也不要求提供 `python3 -m product` 入口。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `portfolio-council-orchestration`：要求由仓库内 Codex-native Skill 和独立 LLM Agent 定义执行固定 fixture Council 链路，使用 Gate-scoped 只读 MCP，并提供可重复 Smoke 入口和可审计终态。
- `specialist-research`：要求 Company Analyst 与 Skeptic 使用独立 LLM 上下文、实际纳入专业 Skills 的调用指令包、通过结构化契约交换结果，禁止 callback 模拟和硬编码投资结论。
- `point-in-time-evidence`：在研究前强制过滤未来/过期事实，区分机械证据门禁与 LLM 证据判断，并对 Agent 报告和最终决策执行 Evidence Closure；悬空引用属于系统校验失败。
- `decision-trace-evaluation`：记录真实 Agent、Skill instruction bundle、Prompt、显式模型、Codex 事件、MCP 工具调用和 Risk 事件，支持同一 fixture 运行的确定性重建，并让 Eval 消费真实运行产物而不预设投资结论。
- `advisory-decision-output`：定义成功、合法 NO_TRADE 和校验失败的不同产物规则，确保机器决策、人类报告与错误产物不会相互冒充。

## Impact

- 影响 `product/skills/portfolio-council`、`product/.codex/agents/runtime_*`、Codex Plugin/Agent Package 配置、fixture-only MCP 配置，以及固定 fixture 的 Codex-native 发现与启动方式。
- 影响 Evidence Gate、Agent Research Report、Final Decision Plan、Decision Trace、结构化运行错误、Codex JSONL 事件和 Eval/Smoke 产物契约及其验证测试。
- 保留现有 Python Evidence、Schema、数学、持仓核算、Risk Engine、验证和存储模块；Python 不获得 LLM 编排或投资判断职责。
- 不接入真实行情、SEC、FRED、期权、多市场、动态 Agent 路由、券商/订单能力或 Reflection Agent。
